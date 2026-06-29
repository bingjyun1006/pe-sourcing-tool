#!/usr/bin/env python3
"""
EMS Librarian — PE KM Tool 核心調度腳本
Usage:
  python librarian.py --new-track "半導體先進封裝"   # 建立研究簡報
  python librarian.py --watch                        # 啟動 Watchdog 監控
  python librarian.py --new-track "半導體先進封裝" --watch  # 兩者同時
"""

import argparse
import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Literal

import requests
import urllib3
import yaml
import pdfplumber
import anthropic
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Windows 終端機 UTF-8 輸出
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─── 環境設定 ────────────────────────────────────────────────────
load_dotenv()
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY")

BASE_DIR       = Path(__file__).parent
VAULT_DIR      = BASE_DIR / "Obsidian_Vault" / "01_Fact_Hunter"
RAW_INPUTS_DIR = VAULT_DIR / "raw_inputs"
TRACK_TREES_DIR= VAULT_DIR / "track_trees"
TRACKS_YAML    = BASE_DIR / "tracks.yaml"
PROCESSED_JSON = BASE_DIR / "processed_files.json"
LOG_FILE       = BASE_DIR / "processing.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

client        = genai.Client(api_key=GEMINI_API_KEY)


def set_gemini_api_key(key: str) -> None:
    """動態替換 Gemini API Key（供 UI 層在使用者輸入後呼叫）"""
    global client
    client = genai.Client(api_key=key.strip())


# ─── Pydantic 資料結構 ───────────────────────────────────────────
class ExtractedEntity(BaseModel):
    entity_name: str = Field(description="未上市或興櫃公司之法定全稱或明確簡稱")
    business_description: str = Field(description="一句話（20字以內）說明此公司的核心業務，例：提供 CoWoS 製程用 ABF 基板")
    source_type: Literal[
        "Annual_Report", "CSR_Report", "Financial_Statement",
        "Gov_Grant", "Exhibition", "Job_Posting"
    ]
    evidence_quote: str = Field(description="100% 複製原文之關鍵事實文本")
    page_number: int = Field(description="年報/財報頁碼；文字檔填 0")
    context_relation: str = Field(description="與來源公司的物理事實關係")
    unlisted_evidence: str = Field(description="文件中支持此公司為未上市／興櫃的原文依據")
    confidence: Literal["high", "medium", "low"]
    relation_category: str = Field(default="", description="T1：供應商/原料廠商/合作廠商；T2：子公司/關聯企業/被投資公司")
    source_section: str = Field(default="", description="該公司出現的段落或附表標題原文")

class TrackTreePayload(BaseModel):
    source_company: str
    track_name: str
    discovered_entities: List[ExtractedEntity]

class CompanyRec(BaseModel):
    company_name: str
    ticker: str
    reason: str

class BriefRecommendations(BaseModel):
    track1: List[CompanyRec]
    track2: List[CompanyRec]

class SkeletonLayer(BaseModel):
    level: int
    name: str
    description: str
    known_companies: List[str] = []
    out_of_scope: bool = False

class SkeletonMap(BaseModel):
    total_layers: int
    layers: List[SkeletonLayer]


# ─── 設定載入 ────────────────────────────────────────────────────
def load_tracks() -> dict:
    with open(TRACKS_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["tracks"]

def load_processed() -> set:
    if PROCESSED_JSON.exists():
        with open(PROCESSED_JSON, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_processed(processed: set):
    with open(PROCESSED_JSON, "w", encoding="utf-8") as f:
        json.dump(list(processed), f, ensure_ascii=False)


# ─── Gemini 呼叫 ─────────────────────────────────────────────────
def gemini_text(prompt: str, retries: int = 3, temperature: float = 0.1) -> str:
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                )
            )
            return response.text
        except Exception as e:
            if attempt < retries - 1 and ("503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e)):
                wait = (attempt + 1) * 15  # 15s, 30s, 45s
                log.warning(f"Gemini 暫時過載，{wait} 秒後重試（第 {attempt+1} 次）")
                time.sleep(wait)
            else:
                raise

def gemini_pdf(pdf_path: Path, prompt: str, retries: int = 3, temperature: float = 0.1) -> str:
    import shutil, tempfile, unicodedata, re as _re

    # Gemini SDK 把檔名放進 HTTP header，header 只接受 ASCII
    # 若檔名含非 ASCII 字元（如中文），先複製到暫存 ASCII 路徑
    safe_name = unicodedata.normalize("NFKD", pdf_path.name).encode("ascii", "ignore").decode("ascii")
    safe_name = _re.sub(r'[^\w.\-]', '_', safe_name).strip("_.")
    if not safe_name or safe_name.lower() == "pdf":
        safe_name = "upload"
    if not safe_name.endswith(".pdf"):
        safe_name += ".pdf"

    tmp_dir = None
    upload_path = pdf_path
    if safe_name != pdf_path.name:
        tmp_dir = Path(tempfile.mkdtemp())
        upload_path = tmp_dir / safe_name
        shutil.copy2(pdf_path, upload_path)
        log.info(f"中文檔名暫存為 ASCII：{safe_name}")

    try:
        log.info(f"上傳 PDF 至 Gemini：{pdf_path.name}")
        uploaded = client.files.upload(file=upload_path, config={"mime_type": "application/pdf"})
        for attempt in range(retries):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[uploaded, prompt],
                    config=types.GenerateContentConfig(temperature=0),
                )
                return response.text
            except Exception as e:
                if attempt < retries - 1 and ("503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e)):
                    wait = (attempt + 1) * 15
                    log.warning(f"Gemini PDF 暫時過載，{wait} 秒後重試（第 {attempt+1} 次）")
                    time.sleep(wait)
                else:
                    raise
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

SEARCH_CACHE_DIR    = BASE_DIR / "data" / "searches"
SAVED_TRACKS_FILE   = BASE_DIR / "data" / "saved_tracks.json"
TWSE_DB_FILE        = BASE_DIR / "data" / "twse_companies.json"
PROCESSED_FILES_JSON  = BASE_DIR / "data" / "processed_files.json"   # 舊全域檔（向下相容）
FILE_SOURCE_TYPES_JSON = BASE_DIR / "data" / "file_source_types.json"  # 舊全域檔（向下相容）
BRIEFS_DIR            = BASE_DIR / "data" / "company_briefs"
PDFS_DIR              = BASE_DIR / "data" / "pdfs"


def _safe_track(track_name: str) -> str:
    """賽道名稱轉為安全檔名"""
    return track_name.replace("/", "_").replace("\\", "_").replace(" ", "_")[:40]

def get_track_pdf_dir(track_name: str) -> Path:
    """賽道專屬 PDF 儲存目錄"""
    return PDFS_DIR / _safe_track(track_name)

def get_track_processed_path(track_name: str) -> Path:
    return BASE_DIR / "data" / f"processed_files_{_safe_track(track_name)}.json"

def get_track_source_types_path(track_name: str) -> Path:
    return BASE_DIR / "data" / f"file_source_types_{_safe_track(track_name)}.json"


def load_file_source_types(track_name: str = None) -> dict:
    """讀取 {filename: source_type} 對應表；有 track_name 則讀賽道專屬檔"""
    path = get_track_source_types_path(track_name) if track_name else FILE_SOURCE_TYPES_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_file_source_type(filename: str, source_type: str, track_name: str = None) -> None:
    """記錄某份 PDF 的軌道類型；有 track_name 則存賽道專屬檔"""
    mapping = load_file_source_types(track_name)
    mapping[filename] = source_type
    path = get_track_source_types_path(track_name) if track_name else FILE_SOURCE_TYPES_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")


def load_processed_files(track_name: str = None) -> set:
    """讀取已處理過的 PDF 紀錄；有 track_name 則讀賽道專屬檔"""
    path = get_track_processed_path(track_name) if track_name else PROCESSED_FILES_JSON
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_processed_files(processed: set, track_name: str = None) -> None:
    """將已處理的 PDF 紀錄寫回磁碟；有 track_name 則存賽道專屬檔"""
    path = get_track_processed_path(track_name) if track_name else PROCESSED_FILES_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sorted(processed), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_company_brief(company_name: str) -> dict | None:
    """從磁碟讀取公司簡介快取，無則回傳 None"""
    safe = re.sub(r'[\\/:*?"<>|]', "_", company_name)[:60]
    p = BRIEFS_DIR / f"{safe}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_company_brief(company_name: str, data: dict) -> None:
    """將公司簡介快取寫入磁碟"""
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', "_", company_name)[:60]
    p = BRIEFS_DIR / f"{safe}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


_CHINA_CITIES = (
    # 直轄市 / 省份通稱
    "中國", "大陸", "內地",
    "安徽", "廣東", "廣西", "湖南", "湖北", "浙江", "江蘇", "四川",
    "遼寧", "吉林", "黑龍江", "山東", "河北", "河南", "陝西", "山西",
    "貴州", "雲南", "福建", "江西", "海南", "甘肅",
    # 主要城市
    "上海", "北京", "深圳", "廣州", "蘇州", "無錫", "昆山",
    "惠州", "成都", "武漢", "杭州", "南京", "天津", "重慶", "東莞",
    "廈門", "青島", "西安", "大連", "寧波", "珠海", "佛山", "中山",
    "濟南", "瀋陽", "長沙", "合肥", "福州", "鄭州", "南昌", "宜昌",
    "煙台", "溫州", "泉州", "常州", "南通", "嘉興",
    # 補充（日誌中實際出現的漏網城市）
    "北海", "嘉善", "株洲", "長春", "哈爾濱", "石家莊", "太原",
    "昆明", "貴陽", "南寧", "拉薩", "烏魯木齊", "呼和浩特",
    "徐州", "鹽城", "揚州", "鎮江", "泰州", "台州", "紹興", "金華",
    "蕪湖", "馬鞍山", "淮南", "滁州", "漳州", "泉州", "三明",
    "贛州", "九江", "萍鄉", "景德鎮", "吉安", "撫州",
)

# 韓國、大陸的公司法律形式後綴（日本 株式会社 刻意保留：日本隱形冠軍具 PE 投資價值）
_FOREIGN_SUFFIXES = (
    "주식회사",               # 韓國
    "有限责任公司",            # 簡體大陸
    "有限責任公司",            # 繁體大陸
)


def is_foreign_company(name: str) -> bool:
    """
    判斷是否為外國/海外公司，供後處理過濾使用。
    設計原則：優先識別結構特徵，不依賴城市名單枚舉（因為大陸城市太多）。

    規則（依序）：
    1. 零中文字 → 外國公司（全英文、日文假名等）
    2. 含韓文字元 → 韓國公司
    3. 明確外國法律形式後綴（韓國、大陸有限责任公司）
    4. 括號內含港澳地名 → 香港/澳門實體
    5. 【結構識別】(地名)有限公司 pattern（不含「股份」）→ 大陸製造子公司命名慣例
       台灣公司幾乎都是「股份有限公司」；「(地名)有限公司」格式幾乎專屬大陸子公司
    6. 大陸城市/省份名稱（補充，覆蓋無括號的大陸公司）
    """
    n = name.strip()

    # 1. 完全無中文字
    if not any('一' <= c <= '鿿' for c in n):
        return True

    # 2. 含韓文字元
    if any('가' <= c <= '힯' for c in n):
        return True

    # 3. 明確外國法律形式後綴
    if any(s in n for s in _FOREIGN_SUFFIXES):
        return True

    # 4. 名稱中含港澳地名（含括號內或直接嵌入，如「冠銓香港(股)公司」）
    _HK_MACAO = ("香港", "澳門", "Hong Kong", "Macau", "Macao")
    if any(loc in n for loc in _HK_MACAO):
        return True

    # 5. 【核心結構規則】有限公司（不含「股份」）→ 非台灣目標
    #    台灣 PE 標的幾乎 100% 是「股份有限公司」。
    #    「有限公司」（無股份）在附表七出現的幾乎都是大陸製造子公司或境外實體。
    #    此規則是正向識別台灣公司（股份有限公司），而非枚舉壞的，具 MECE 性。
    #    例外：日本 株式会社 已在規則 3 前被保留（未列入 _FOREIGN_SUFFIXES）。
    if n.endswith("有限公司") and "股份" not in n:
        return True

    # 6. 大陸城市/省份名稱（保留作為備用防線，覆蓋少數命名不標準的大陸公司）
    if any(city in n for city in _CHINA_CITIES):
        return True

    return False


def load_twse_candidate_pool() -> str:
    """
    載入 TWSE/OTC 台灣上市/上櫃公司候選池。
    篩選股票代號 2000-8999（電子/科技/半導體相關公司集中區間）。
    回傳格式："代號簡稱" 以頓號分隔的字串，供骨架地圖 prompt 使用。
    """
    try:
        if not TWSE_DB_FILE.exists():
            log.warning("twse_companies.json 不存在，骨架地圖將不限制候選公司")
            return ""
        db = json.loads(TWSE_DB_FILE.read_text(encoding="utf-8"))
        candidates = []
        for name, info in db.items():
            code = info.get("code", "")
            short = info.get("short_name", name)
            if code.isdigit() and 2000 <= int(code) <= 8999:
                candidates.append(f"{code}{short}")
        candidates.sort()
        log.info(f"TWSE 候選池：{len(candidates)} 家公司")
        return "、".join(candidates)
    except Exception as e:
        log.warning(f"載入 TWSE 候選名單失敗：{e}")
        return ""


def validate_companies_in_twse(companies: list[str]) -> tuple[list[str], list[str]]:
    """
    驗證公司名稱是否在 TWSE/OTC 資料庫中。
    回傳 (已驗證清單, 未找到清單)。
    """
    if not TWSE_DB_FILE.exists():
        return companies, []
    try:
        db = json.loads(TWSE_DB_FILE.read_text(encoding="utf-8"))
        # 建立 short_name → full_name 的快速查找表
        short_to_full: dict[str, str] = {}
        for full, info in db.items():
            short = info.get("short_name", "")
            if short:
                short_to_full[short] = full
            short_to_full[full] = full  # full name also valid

        verified, not_found = [], []
        for co in companies:
            if co in short_to_full or co in db:
                verified.append(co)
            else:
                # 模糊比對：公司名包含在資料庫某個名稱中
                fuzzy = next((s for s in short_to_full if co in s or s in co), None)
                if fuzzy:
                    verified.append(co)
                else:
                    not_found.append(co)
        return verified, not_found
    except Exception as e:
        log.warning(f"TWSE 驗證失敗：{e}")
        return companies, []

def save_search_result(keyword: str, skeleton_map, recommendations, track3: dict) -> Path:
    """將搜尋結果存成 JSON，供下次啟動時讀回（不用重跑 Gemini）"""
    SEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_kw = keyword.replace("/", "_").replace(" ", "_").replace("\\", "_")[:30]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SEARCH_CACHE_DIR / f"{safe_kw}_{timestamp}.json"
    data = {
        "keyword":         keyword,
        "timestamp":       datetime.now().isoformat(),
        "skeleton_map":    skeleton_map.model_dump() if skeleton_map else None,
        "recommendations": recommendations.model_dump() if recommendations else None,
        "track3":          track3,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"搜尋結果已存：{path.name}")
    return path

def save_track(keyword: str, search_filename: str = "") -> List[dict]:
    """將關鍵字儲存為已追蹤賽道，並同步寫入 tracks.yaml 確保資料不跨賽道污染"""
    tracks = load_saved_tracks()
    # 避免重複
    if any(t["keyword"] == keyword for t in tracks):
        return tracks
    tracks.append({
        "keyword":      keyword,
        "saved_at":     datetime.now().isoformat(),
        "search_file":  search_filename,
    })
    SAVED_TRACKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SAVED_TRACKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tracks, f, ensure_ascii=False, indent=2)

    # 同步寫入 tracks.yaml（若此關鍵字尚未定義）
    _sync_keyword_to_tracks_yaml(keyword)

    return tracks


def _sync_keyword_to_tracks_yaml(keyword: str) -> None:
    """確保 keyword 在 tracks.yaml 有對應設定，沒有則自動新增"""
    try:
        with open(TRACKS_YAML, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        existing = data.get("tracks", {})
        # 已存在：name 完全吻合即視為已有
        if any(v.get("name") == keyword for v in existing.values()):
            return
        # 產生安全 key（英數底線）
        import unicodedata, re as _re
        safe_key = unicodedata.normalize("NFKD", keyword).encode("ascii", "ignore").decode("ascii")
        safe_key = _re.sub(r"[^\w]", "_", safe_key).strip("_")[:40] or f"track_{len(existing)}"
        # 避免 key 衝突
        base_key = safe_key
        i = 2
        while safe_key in existing:
            safe_key = f"{base_key}_{i}"
            i += 1
        safe_name = keyword.replace("/", "_").replace("\\", "_").replace(" ", "_")[:40]
        existing[safe_key] = {
            "name":            keyword,
            "file_keywords":   [keyword],
            "search_keywords": [keyword],
            "tree_file":       f"{safe_name}賽道.md",
        }
        data["tracks"] = existing
        with open(TRACKS_YAML, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        log.info(f"tracks.yaml 新增賽道：{keyword} → {safe_name}賽道.md")
    except Exception as e:
        log.warning(f"同步 tracks.yaml 失敗（不影響主流程）：{e}")

def load_saved_tracks() -> List[dict]:
    """讀取已儲存的賽道清單"""
    if not SAVED_TRACKS_FILE.exists():
        return []
    try:
        with open(SAVED_TRACKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def delete_track(keyword: str) -> List[dict]:
    """刪除已儲存的賽道"""
    tracks = [t for t in load_saved_tracks() if t["keyword"] != keyword]
    with open(SAVED_TRACKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tracks, f, ensure_ascii=False, indent=2)
    return tracks

def rename_track_label(keyword: str, new_label: str) -> List[dict]:
    """更新已儲存賽道的顯示名稱，不影響內部 keyword 及相關檔案路徑"""
    tracks = load_saved_tracks()
    for t in tracks:
        if t["keyword"] == keyword:
            t["label"] = new_label.strip()
            break
    with open(SAVED_TRACKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tracks, f, ensure_ascii=False, indent=2)
    return tracks

def load_search_history() -> List[dict]:
    """讀取所有歷史搜尋記錄（按時間倒序）"""
    if not SEARCH_CACHE_DIR.exists():
        return []
    history = []
    for fp in sorted(SEARCH_CACHE_DIR.glob("*.json"), reverse=True):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            history.append({
                "filename":  fp.name,
                "keyword":   data.get("keyword", ""),
                "timestamp": data.get("timestamp", "")[:16].replace("T", " "),
                "path":      str(fp),
                "data":      data,
            })
        except Exception:
            continue
    return history

def delete_version(path: str) -> bool:
    """刪除指定路徑的版本 JSON 檔"""
    try:
        p = Path(path)
        if p.exists() and p.suffix == ".json" and p.parent == SEARCH_CACHE_DIR:
            p.unlink()
            return True
    except Exception:
        pass
    return False


def list_versions_for_keyword(keyword: str) -> List[dict]:
    """
    列出特定關鍵字的所有歷史版本，按時間倒序排列。
    回傳 list of {"label": 顯示文字, "path": 檔案路徑, "data": 完整 JSON}
    """
    if not SEARCH_CACHE_DIR.exists():
        return []
    safe_kw = keyword.replace("/", "_").replace(" ", "_").replace("\\", "_")[:30]
    versions = []
    for fp in sorted(SEARCH_CACHE_DIR.glob(f"{safe_kw}_*.json"), reverse=True):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            ts_raw = data.get("timestamp", "")
            ts = ts_raw[:16].replace("T", " ") if ts_raw else fp.stem[-15:].replace("_", " ")
            versions.append({
                "label": ts,
                "path":  str(fp),
                "data":  data,
            })
        except Exception:
            continue
    return versions


def load_company_details(tree_file: Path) -> dict:
    """
    讀取 _details.json，以 entity_name 為 key。
    同一公司名稱保留最新一筆（後寫入的 override 前面的）。
    """
    details_file = tree_file.with_name(tree_file.stem + "_details.json")
    if not details_file.exists():
        return {}
    try:
        records = json.loads(details_file.read_text(encoding="utf-8"))
        result = {}
        for rec in records:
            name = rec.get("entity_name", "").strip()
            if name:
                result[name] = rec
        return result
    except Exception:
        return {}


def generate_company_brief(
    company_name: str,
    evidence_quote: str = "",
    source_type: str = "",
) -> dict:
    """
    使用 Gemini Search Grounding 查詢公司簡介。
    回傳 dict: business_overview, founded_year, company_size,
               main_products, main_clients, sources
    """
    context_hint = ""
    if evidence_quote and evidence_quote not in ("文件直接點名", "", "業務不明"):
        context_hint = f"\n參考背景：此公司在財務文件中的記錄：「{evidence_quote[:200]}」"

    prompt = f"""請搜尋台灣公司「{company_name}」的基本資料，只回傳以下 JSON，不要任何說明文字或 markdown：

{{
  "business_overview": "2-3句業務概述，說明公司核心業務",
  "founded_year": "成立年份，例：1998年。查無則填「查無資料」",
  "company_size": "公司規模，例：員工約X人、資本額X億。查無則填「查無資料」",
  "main_products": ["主要產品或服務1", "主要產品或服務2"],
  "main_clients": ["主要客戶1", "主要客戶2"]
}}
{context_hint}
規則：查無任何欄位資料一律填「查無資料」；main_products / main_clients 查無則填 ["查無資料"]；不得推測或捏造。"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        raw = response.text.strip()
        # 清除 markdown code block
        if "```" in raw:
            raw = re.sub(r"```[a-z]*\n?", "", raw).replace("```", "").strip()

        data = json.loads(raw)

        # 提取 grounding 來源（全部，去重）
        sources = []
        try:
            chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
            seen = set()
            for chunk in chunks:
                if hasattr(chunk, "web") and chunk.web:
                    uri   = getattr(chunk.web, "uri", "") or ""
                    title = getattr(chunk.web, "title", "") or uri
                    if uri and uri not in seen:
                        seen.add(uri)
                        sources.append({"title": title, "uri": uri})
        except Exception:
            pass

        data["sources"] = sources
        return data

    except Exception as e:
        log.warning(f"公司簡介查詢失敗（{company_name}）：{type(e).__name__}: {e}")
        return {
            "business_overview": "查詢失敗，請稍後重試",
            "founded_year": "查無資料",
            "company_size": "查無資料",
            "main_products": ["查無資料"],
            "main_clients": ["查無資料"],
            "sources": [],
        }


def clean_json(raw: str) -> str:
    """清理 Gemini 回傳的 JSON（去除 markdown code block）"""
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def _safe_json_parse(raw: str) -> dict | None:
    """
    先嘗試標準解析；若失敗（常見原因：Gemini 輸出過長導致 JSON 截斷），
    嘗試截斷修復：找最後一個完整 discovered_entities 元素的邊界並補上結尾。
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_err:
        log.warning(f"JSON 解析失敗，嘗試截斷修復：{first_err}")
        # 找最後一個完整 entity（以 '}' 結尾的陣列元素）
        # 策略：截到最後一個完整的 '}, {' 或 '}]' 邊界
        brace_depth = 0
        last_safe_pos = 0
        in_str = False
        escape = False
        for i, ch in enumerate(raw):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_str:
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == '{':
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 1:
                    # 剛關閉一個 entity 物件（depth 回到 1 = 在 discovered_entities 陣列層）
                    last_safe_pos = i + 1
        if last_safe_pos > 0:
            truncated = raw[:last_safe_pos] + "]}"
            try:
                data = json.loads(truncated)
                n = len(data.get("discovered_entities", []))
                log.info(f"截斷修復成功：保留 {n} 個 entities")
                return data
            except Exception as e2:
                log.warning(f"截斷修復仍失敗：{e2}")
        return None


# ─── 軌道三：爬取 ────────────────────────────────────────────────
TIIP_CACHE         = BASE_DIR / "data" / "tiip_cache.json"
SBIR_CACHE         = BASE_DIR / "data" / "sbir_cache.json"
PROCUREMENT_CACHE  = BASE_DIR / "data" / "procurement_cache.json"
LISTED_CACHE       = BASE_DIR / "data" / "listed_companies.json"
CACHE_MAX_AGE_DAYS = 7

def build_listed_companies_cache():
    """下載 TWSE/OTC/興櫃 公司名單，存成本機 JSON（MVP 一次性執行）"""
    LISTED_CACHE.parent.mkdir(parents=True, exist_ok=True)
    sources = {
        "上市": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "上櫃": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",
        "興櫃": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=5",
    }
    companies = {}  # {"台積電": {"code": "2330", "market": "上市"}}

    for market, url in sources.items():
        print(f"⏳ 下載{market}名單...")
        try:
            resp = requests.get(url, timeout=20, verify=False)
            resp.encoding = "big5"
            soup = BeautifulSoup(resp.text, "html.parser")
            count = 0
            for row in soup.find_all("tr"):
                cols = row.find_all("td")
                if not cols:
                    continue
                # bgcolor 在 <td> 上，不在 <tr> 上
                first_bg = cols[0].get("bgcolor", "").upper()
                if first_bg not in ["#FAFAD2", "#F0F0F0"]:
                    continue
                cell = cols[0].get_text(strip=True)   # e.g. "2330　台積電"
                if "　" in cell:                        # 全形空白分隔
                    code, name = cell.split("　", 1)
                    code = code.strip()
                    name = name.strip().rstrip("*").strip()  # 去除星號標記
                    # 只保留 4 位數純數字代碼（排除 ETF/權證/債券）
                    if name and len(code) == 4 and code.isdigit() and int(code) >= 1000:
                        companies[name] = {"code": code, "market": market}
                        count += 1
            print(f"   {market}：{count} 家")
        except Exception as e:
            log.warning(f"{market} 名單下載失敗：{e}")

    with open(LISTED_CACHE, "w", encoding="utf-8") as f:
        json.dump(companies, f, ensure_ascii=False, indent=2)
    print(f"✅ 上市公司名單建立完成：共 {len(companies)} 家 → {LISTED_CACHE}")
    return companies

_twse_db_cache: dict | None = None

def _load_twse_db() -> dict:
    """
    合併兩個來源：
    - twse_companies.json：全稱為 key，含 short_name/market/industry
    - listed_companies.json：簡稱為 key，含 market
    兩者都有時 twse_companies.json 優先；listed_companies.json 補充其缺少的公司（如興櫃）。
    """
    global _twse_db_cache
    if _twse_db_cache is not None:
        return _twse_db_cache

    merged: dict = {}

    # 先載入 listed_companies.json（簡稱→market），轉換成統一格式
    if LISTED_CACHE.exists():
        with open(LISTED_CACHE, "r", encoding="utf-8") as f:
            listed = json.load(f)
        for short_name, info in listed.items():
            merged[short_name] = {
                "code":       info.get("code", ""),
                "short_name": short_name,
                "market":     info.get("market", ""),
            }

    # 再載入 twse_companies.json（全稱→{short_name, market, ...}），覆蓋同名項目
    if TWSE_DB_FILE.exists():
        with open(TWSE_DB_FILE, "r", encoding="utf-8") as f:
            twse = json.load(f)
        for full_name, info in twse.items():
            merged[full_name] = info
            # 也用 short_name 建索引，方便後續比對
            short = info.get("short_name", "")
            if short and short not in merged:
                merged[short] = info

    _twse_db_cache = merged
    log.info(f"TWSE DB 載入完成：{len(merged)} 筆（含上市/上櫃/興櫃）")
    return _twse_db_cache

def _canon(name: str) -> str:
    """
    將公司名稱化簡為「品牌核心名」，供雙向比對使用。
    兩邊（查詢名稱 & 資料庫）都用同一個函式化簡，格式差異就消失。
    規則：移除所有括號內容 → 移除法律後綴 → 去頭尾空白
    """
    n = name.strip()
    # 移除所有括號內容（含 (股)、(欣興)、（智原）等）
    n = re.sub(r'[\(（][^)）]*[\)）]', '', n)
    # 移除法律後綴
    for suffix in ("股份有限公司", "有限公司", "股份公司", "股份", "公司"):
        if n.endswith(suffix):
            n = n[:-len(suffix)]
            break
    return n.strip()


def get_listing_status(name: str) -> str:
    """
    查詢公司上市狀態。
    查詢邏輯（依序）：
    1. 精確全稱比對
    2. 品牌核心名（canon）對 DB 裡的 canon 索引
    3. short_name 精確比對
    4. 子字串模糊比對（保底）
    """
    if not name:
        return "未上市"
    db = _load_twse_db()

    # 1. 精確全稱比對
    if name in db:
        return db[name]["market"]

    # 2. 品牌核心名比對：把查詢名稱和 DB 全稱都 canon 化後比對
    query_canon = _canon(name)
    if query_canon:
        for full_name, info in db.items():
            if _canon(full_name) == query_canon:
                return info["market"]
            short = info.get("short_name", "")
            if short and _canon(short) == query_canon:
                return info["market"]

    # 3. 子字串模糊比對（處理部分名稱或多出廠別資訊的情況）
    if len(query_canon) >= 2:
        for full_name, info in db.items():
            db_canon = _canon(full_name)
            short = info.get("short_name", "")
            if query_canon in db_canon or (short and query_canon in _canon(short)):
                return info["market"]

    return "未上市"

def lookup_tiip(company_name: str):
    """查詢公司是否有 TIIP 補助紀錄，回傳第一筆或 None"""
    if not TIIP_CACHE.exists():
        return None
    try:
        with open(TIIP_CACHE, "r", encoding="utf-8") as f:
            records = json.load(f)
        for r in records:
            cached = r.get("company", "")
            # 精確比對或包含比對（處理全稱/簡稱差異）
            if (company_name == cached
                    or (len(company_name) >= 3 and company_name in cached)
                    or (len(cached) >= 3 and cached in company_name)):
                return r
        return None
    except Exception:
        return None

def _cache_is_fresh(cache_path: Path) -> bool:
    if not cache_path.exists():
        return False
    age = (datetime.now().timestamp() - cache_path.stat().st_mtime) / 86400
    return age < CACHE_MAX_AGE_DAYS

def build_tiip_cache(max_pages: int = 113):
    """爬取 TIIP 全部頁面並存 cache（約 1-2 分鐘）"""
    TIIP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    url = "https://eii.nat.gov.tw/tiip/achievementList.php"
    all_records = []
    print(f"⏳ 建立 TIIP cache（最多 {max_pages} 頁）...")

    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(url, params={"page": page}, timeout=15, verify=False)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")
            if not tables:
                break
            rows = tables[0].find_all("tr")
            page_data = []
            for row in rows:
                cols = row.find_all("td")
                # 加 page 參數後：6 欄，col[0]=類別, col[1]=年度, col[2]=公司, col[3]=計畫
                if len(cols) >= 4:
                    company = cols[2].get_text(strip=True)
                    project = cols[3].get_text(strip=True)
                    year    = cols[1].get_text(strip=True)
                    type_   = cols[0].get_text(strip=True)
                    if company and len(company) >= 2 and not company.startswith("公司"):
                        page_data.append({
                            "company": company,
                            "project": project,
                            "year":    year,
                            "type":    type_,
                        })
            if not page_data:
                break
            all_records.extend(page_data)
            if page % 10 == 0:
                print(f"   第 {page} 頁，目前 {len(all_records)} 筆...")
            time.sleep(0.3)  # 禮貌性等待
        except Exception as e:
            log.warning(f"TIIP 第 {page} 頁失敗：{e}")
            break

    with open(TIIP_CACHE, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False)
    print(f"✅ TIIP cache 建立完成：{len(all_records)} 筆")
    return all_records

def crawl_tiip(keywords: List[str]) -> List[dict]:
    """TIIP 產發署補助名單（從本機 cache 過濾）"""
    # 載入或重建 cache
    if _cache_is_fresh(TIIP_CACHE):
        with open(TIIP_CACHE, "r", encoding="utf-8") as f:
            all_records = json.load(f)
    else:
        all_records = build_tiip_cache(max_pages=20)  # 首次快速建 cache（前 20 頁）

    # 關鍵字過濾（計畫名稱 or 公司名稱）
    results = []
    for r in all_records:
        text = r.get("project", "") + r.get("company", "")
        matched = [kw for kw in keywords if kw in text]
        if matched:
            results.append({
                "source": "TIIP",
                "company": r["company"],
                "project": r["project"],
                "year":    r["year"],
                "keyword": matched[0]
            })
    return _dedup(results)

def build_sbir_cache(max_pages: int = 30):
    """爬取 SBIR 核定名單並存 cache（支援分頁，自動停止）"""
    SBIR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    all_records = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    print(f"⏳ 建立 SBIR cache（最多 {max_pages} 頁）...")

    for page in range(1, max_pages + 1):
        try:
            url = f"https://sbir.org.tw/sbir/approved?page={page}"
            resp = requests.get(url, timeout=15, verify=False, headers=headers)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            page_records = []
            # 掃描所有 table，找含公司名稱的那張
            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                for row in rows[1:]:  # 跳過 header
                    cols = row.find_all("td")
                    if len(cols) < 2:
                        continue
                    company = cols[0].get_text(strip=True)
                    project = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                    year    = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                    # 過濾：至少 2 字、不是表頭文字
                    if (company and len(company) >= 2
                            and company not in ("公司名稱", "廠商名稱", "企業名稱")):
                        page_records.append({
                            "company": company,
                            "project": project,
                            "year":    year,
                        })

            if not page_records:
                print(f"   第 {page} 頁無資料，停止爬取")
                break

            all_records.extend(page_records)
            print(f"   第 {page} 頁：{len(page_records)} 筆，累計 {len(all_records)} 筆")
            time.sleep(0.5)

        except Exception as e:
            log.warning(f"SBIR 第 {page} 頁失敗：{e}")
            break

    # 去除重複（同公司同計畫）
    seen, unique = set(), []
    for r in all_records:
        key = (r["company"], r["project"][:20])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    with open(SBIR_CACHE, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False)
    print(f"✅ SBIR cache 建立完成：{len(unique)} 筆（去重後）")
    return unique

def crawl_sbir(keywords: List[str]) -> List[dict]:
    """SBIR 中小企業署核定名單（從本機 cache 過濾）"""
    if _cache_is_fresh(SBIR_CACHE):
        with open(SBIR_CACHE, "r", encoding="utf-8") as f:
            all_records = json.load(f)
    else:
        all_records = build_sbir_cache()

    results = []
    for r in all_records:
        text = r.get("project", "") + r.get("company", "")
        matched = [kw for kw in keywords if kw in text]
        if matched:
            results.append({
                "source": "SBIR",
                "company": r["company"],
                "project": r["project"],
                "year":    r["year"],
                "keyword": matched[0]
            })
    return _dedup(results)

def _dedup(items: List[dict]) -> List[dict]:
    seen, unique = set(), []
    for r in items:
        if r["company"] and r["company"] not in seen:
            seen.add(r["company"])
            unique.append(r)
    return unique

def _search_procurement_keyword(keyword: str, session: requests.Session) -> List[dict]:
    """單一關鍵字搜尋政府採購網決標公告"""
    results = []
    url = "https://web.pcc.gov.tw/prkms/tender/common/tenderSearch/search"
    params = {
        "searchType": "advance",
        "tenderName": keyword,
        "tenderStatus": "2",   # 2 = 決標
        "tenderMethod": "",
        "tenderOrg": "",
    }
    try:
        resp = session.get(url, params=params, timeout=20)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # 找結果表格（最大、有多行的表格）
        result_table = None
        for t in soup.find_all("table"):
            if len(t.find_all("tr")) > 2:
                result_table = t
                break
        if not result_table:
            log.info(f"政府採購網：{keyword} — 找不到結果表格")
            return results

        rows = result_table.find_all("tr")[1:]  # 跳過表頭
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue
            texts = [c.get_text(strip=True) for c in cols]

            # 找含「公司」字樣的欄位作為廠商名稱
            company, project, agency, year_val = "", "", "", ""
            for i, text in enumerate(texts):
                if any(s in text for s in ["股份有限公司", "有限公司", "股份公司"]):
                    company = text.strip()
                    project = texts[2] if len(texts) > 2 else ""
                    agency  = texts[1] if len(texts) > 1 else ""
                    # 嘗試解析年度（找含年度格式的欄位）
                    for t in texts:
                        if t and len(t) >= 7 and t[:3].isdigit():   # 民國年 e.g. 113/05/01
                            year_val = "民國" + t[:3] + "年"
                            break
                    break

            if company and len(company) >= 4:
                results.append({
                    "source": "政府採購網",
                    "company": company,
                    "project": project,
                    "agency":  agency,
                    "year":    year_val or str(datetime.now().year),
                    "keyword": keyword,
                })

    except Exception as e:
        log.warning(f"政府採購網搜尋失敗（{keyword}）：{e}")

    return results


def crawl_procurement(keywords: List[str]) -> List[dict]:
    """政府採購網 決標公告爬取（信號：已對政府交付，商業化程度高）

    Cache 策略：以關鍵字為 key 存成 JSON，7 天有效
    """
    # 讀現有 cache
    cache_data: dict = {}
    if PROCUREMENT_CACHE.exists():
        try:
            with open(PROCUREMENT_CACHE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception:
            cache_data = {}

    session = requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    })

    all_results: List[dict] = []
    updated = False

    for kw in keywords[:3]:   # 最多 3 個關鍵字，避免過多請求
        if kw in cache_data and isinstance(cache_data[kw], list):
            log.info(f"政府採購網：{kw} 使用 cache（{len(cache_data[kw])} 筆）")
            all_results.extend(cache_data[kw])
            continue

        print(f"⏳ 搜尋政府採購決標公告：{kw}")
        kw_results = _search_procurement_keyword(kw, session)
        cache_data[kw] = kw_results
        all_results.extend(kw_results)
        updated = True
        time.sleep(1.5)   # 禮貌性延遲

    if updated:
        PROCUREMENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROCUREMENT_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 政府採購 cache 更新：{len(all_results)} 筆")

    deduped = _dedup(all_results)
    log.info(f"政府採購網結果：{len(deduped)} 家廠商")
    return deduped


def crawl_track3(keywords: List[str]) -> dict:
    return {
        "tiip":        crawl_tiip(keywords),
        "sbir":        crawl_sbir(keywords),
        "procurement": crawl_procurement(keywords),
    }


def suggest_scene_contexts(keyword: str) -> list:
    """根據使用者輸入的關鍵字，建議 3-4 個應用場景 chips。
    自動判斷輸入類型（賽道 / 公司名稱 / 模糊）；無法判斷時回傳空陣列。
    """
    prompt = f"""你是 PE 投資分析師。用戶輸入「{keyword}」，請：
1. 若為產業賽道（如散熱模組、被動元件、PCB）→ 列出 4 個最主要的下游應用市場
2. 若為公司名稱（如台積電、鴻海）→ 列出該公司 4 個主要業務市場
3. 若輸入過於廣泛、模糊、或與製造業 / 科技業無關 → 回傳空陣列

每個場景限 3-6 字（繁體中文），只回傳 JSON array，無法判斷則回 []
範例：["AI 伺服器", "車用電子", "工業自動化", "消費型 PC"]"""
    try:
        raw = gemini_text(prompt)
        data = json.loads(clean_json(raw))
        if isinstance(data, list):
            return [str(s).strip() for s in data if s and len(str(s).strip()) <= 12][:4]
    except Exception:
        pass
    return []


# ─── 研究簡報生成 ─────────────────────────────────────────────────
def generate_skeleton_map(keyword: str, context: str = "") -> SkeletonMap:
    """Gemini 動態生成供應鏈骨架地圖。
    層數由關鍵字具體程度決定：輸入越 niche → 層數越少。
    L2+ 公司從 TWSE/OTC 驗證名單中選取，避免外國公司或幻覺公司。
    """
    # 載入 TWSE/OTC 候選池（~1400 家台灣上市/上櫃電子科技公司）
    candidate_pool = load_twse_candidate_pool()
    if candidate_pool:
        pool_section = f"""
【台灣上市/上櫃公司候選名單（L2以下必須從此選）】
以下為台灣上市/上櫃公司名單（電子/科技類，代號 2000–8999，共約 {len(candidate_pool.split('、'))} 家）：
{candidate_pool}

**L2 以下層級的 known_companies，只能填入上方名單中出現的公司簡稱或全稱，禁止填入名單以外的任何公司。**
若某層在名單中確實找不到合適的公司，known_companies 填空陣列（[]），不要捏造名單以外的公司。
"""
    else:
        pool_section = ""

    context_section = f"\n【分析角度／應用場景】\n使用者指定：{context}\n請以此作為供應鏈地圖的主要視角，L1 客戶群與各層公司選填須貼合此場景。\n" if context.strip() else ""

    prompt = f"""你是台灣 PE 投資分析師。請為「{keyword}」產業生成供應鏈骨架地圖（JSON）。
{context_section}{pool_section}
【層數規則】
- 輸入越廣泛（如「半導體」）→ 層數越多（4–5 層）
- 輸入越具體（如「CoWoS 底膠材料」）→ 層數越少（2–3 層）
- 最多不超過 5 層

【角色推理（填公司前必須先做這步）】
填入公司前，先為每一層定義一句話的業務角色（例：「提供封裝測試服務的 OSAT 廠商」）。
確認相鄰兩層的業務角色明顯不同，不得將同類型公司分散在不同層。
角色定義完成後，再從符合該角色且**出現在上方名單**中的公司選入。

【各層規則】
- L1：此供應鏈的最終需求方，**恰好 4 家，不多不少**
  - 填入前先識別此賽道的主要應用市場（如消費型 / 企業型 / 工業車用）及各市場的相對採購規模
  - **以採購規模最大、成長動能最強的應用市場為主**：AI 伺服器、資料中心、車用電子的優先順位高於消費型 PC / 手機
  - 若消費型與企業型客戶並存，**企業型（伺服器 ODM、雲端業者、車廠 Tier 1）優先**；消費型品牌最多佔 1–2 席
  - 優先選對此賽道有最直接採購需求的廠商，而非僅有間接關聯的泛用大廠
- L2：直接向 L1 提供核心產品或服務的製造商／服務商，**恰好 4 家，不多不少**
  - 填入前確認 L2 的業務角色與 L1 明顯不同；同類型公司不得同時出現在 L1 和 L2
- L3 以下：若名單中有符合的台灣上市/上櫃公司則填入（最多 4 家），若無則回傳空陣列（[]）
- 最後一層且無已知上市公司時，description 說明這層在供應鏈的角色（此層為本系統挖掘目標）
- 超出分析範圍的層：out_of_scope 設 true，name 填「超出本系統分析涵蓋範圍」，known_companies 回傳 []，description 填空字串
- 每層 description 用一句話說明該層在此供應鏈的角色

【公司選填規則】
1. L1（終端需求方）：可填外國公司（如消費電子品牌、外國晶片設計商）
   L2 以下（製造層）：**只從上方名單中選台灣上市/上櫃公司**，禁止填入三星、英特爾等外國公司
2. 公司名使用名單上的簡稱（如「台積電」「日月光投控」「欣興」）
3. 若某公司已被另一家收購整合，以現存母公司為準（例：矽品已併入日月光，不得同時出現）
4. 同一層各公司不得重複或互為母子關係

【嚴格要求】
- L2+ 只能填名單中出現的公司，名單外的公司一律不填
- 只回傳 JSON，不要有任何其他文字

{{
  "total_layers": 數字,
  "layers": [
    {{
      "level": 1,
      "name": "層名（例：終端市場）",
      "description": "一句話說明此層角色",
      "known_companies": ["公司A", "公司B"],
      "out_of_scope": false
    }}
  ]
}}"""

    raw = gemini_text(prompt)
    data = json.loads(clean_json(raw))
    skeleton = SkeletonMap(**data)

    # 後處理：驗證 L2+ 公司是否都在 TWSE 資料庫中，記錄未驗證的公司
    for layer in skeleton.layers:
        if layer.level <= 1 or layer.out_of_scope or not layer.known_companies:
            continue
        verified, not_found = validate_companies_in_twse(layer.known_companies)
        if not_found:
            log.warning(f"骨架地圖 L{layer.level} 中有 {len(not_found)} 家公司未在 TWSE 資料庫找到：{not_found}")
            # 移除未驗證公司，保留已驗證的
            layer.known_companies = verified

    return skeleton


def generate_recommendations(
    track_name: str,
    keywords: List[str],
    skeleton: "SkeletonMap | None" = None,
    context: str = "",
) -> BriefRecommendations:
    # T1：參考骨架地圖 L2/L3 公司，找年報揭露可能性高的製造商
    # T2：參考骨架地圖大廠找投資組合
    t1_context = ""
    t2_context = ""
    if skeleton:
        t1_lines, t2_lines = [], []
        for layer in skeleton.layers:
            if layer.out_of_scope:
                continue
            if layer.level >= 2:
                examples = "、".join(layer.known_companies[:3]) if layer.known_companies else "暫無已知上市公司"
                line = f"- L{layer.level}（{layer.name}）：{layer.description}（例：{examples}）"
                t1_lines.append(line)
                # T2 context：同樣帶層描述，而非只有公司名稱
                t2_lines.append(line)

        if t1_lines:
            t1_context = (
                f"\n此賽道供應鏈各層角色與已知公司（來自骨架地圖）：\n"
                + "\n".join(t1_lines)
                + "\n請優先從上述層級類型的台灣上市/上櫃公司中選擇（不限於括號內例舉的公司）；"
                + "括號內的例舉僅供參考，若其不符選擇標準則跳過，選擇同層其他符合的公司。"
            )
        if t2_lines:
            t2_context = (
                f"\n此賽道供應鏈結構（來自骨架地圖）：\n"
                + "\n".join(t2_lines)
                + "\n選擇標準以「附表九能揭露最多未上市隱形冠軍」為優先，不以層級高低為限——"
                + "L3/L4 材料或設備廠若持有深層子公司，同樣是高價值目標。"
            )

    # 載入 TWSE 候選池供 T1/T2 推薦使用（與骨架地圖共用同一池）
    candidate_pool = load_twse_candidate_pool()
    if candidate_pool:
        pool_note = (
            f"\n\n【公司名稱限制】\n"
            f"以下為台灣上市/上櫃公司名單（電子/科技類，共約 {len(candidate_pool.split('、'))} 家）：\n"
            f"{candidate_pool}\n"
            f"ticker 欄位請填入上方名單對應的股票代號（4-5 位數字）。"
            f"若推薦名單以外的公司，ticker 請填「-」，並在 reason 說明。"
        )
    else:
        pool_note = ""

    context_line = f"\n【分析角度／應用場景】使用者指定：{context}，請以此為主要視角選擇推薦公司。" if context.strip() else ""

    if True:  # 統一走這條路
        prompt = f"""你是台灣 PE 投資分析師助理。
用戶想研究「{track_name}」賽道的未上市隱形冠軍供應商。
賽道關鍵字：{', '.join(keywords)}{context_line}
{pool_note}
【軌道一（年報）】
目標：找台灣上市/上櫃公司，其年報「主要進貨廠商」章節最可能點名具體的未上市供應商。{t1_context}
選擇標準（依序判斷）：
1. 在此賽道中自行採購原料、零組件或材料並進行生產加工：有實際進貨行為，年報因此有具體供應商可揭露
2. 排除本身不採購實體材料的公司：如將製造完全外包、或主要業務是設計而非生產的公司，其年報供應商欄位通常空泛或無意義
3. 優先選供應鏈中有以下特徵的中型製造商：
   - 自行採購專業原料或零件（有明確的實體進貨行為）
   - 其直接供應商規模小、非業界已知大廠（代表年報有挖掘價值）
   - 非供應鏈頂部的超大型整合廠（其主要供應商通常已是知名上市公司，資訊 alpha 低）
4. 只選台灣上市/上櫃公司，不選外國公司
盡量回傳 5 筆，依年報揭露未上市隱形冠軍的可能性由高到低排序；若真正符合條件的不足 5 家，則給出所有符合的公司，不要為湊數而降低標準

【軌道二（合併財報）】
目標：找在「{track_name}」賽道從事實際生產或服務業務的台灣大型集團，其合併財報附表九最可能揭露此賽道相關的未上市被投資公司。{t2_context}
選擇標準（依序判斷）：
1. 在此賽道有實際生產或服務業務（非純財務投資機構，如投資銀行、PE、VC 等）
2. 有已知的策略投資組合或投資子公司，附表九可能揭露相關未上市被投資公司
3. 排除賽道週邊的服務性廠商（廠房工程、IT、物流等）：即使與此賽道有往來，其附表九被投資公司通常與賽道無關
盡量回傳 5 筆；若真正符合條件的不足 5 家，則給出所有符合的公司，不要為湊數而降低標準

【關鍵規則】同一家公司可以同時出現在 track1 和 track2：
- 若某公司既符合 T1 條件（有實體採購、供應商可能具名），又符合 T2 條件（有子公司投資組合）→ 請同時列入兩個清單
- 使用者會分別取得年報和合併財報，分開上傳到對應軌道，不會重複或衝突
- 不得為了避免重複而只選其中一個清單放；兩個清單各自獨立評估

請只回傳 JSON，不要有任何其他文字：
{{
  "track1": [
    {{"company_name": "公司名", "ticker": "台股代號", "reason": "一句話推薦理由（為何年報可能揭露供應商）"}}
  ],
  "track2": [
    {{"company_name": "公司名", "ticker": "台股代號", "reason": "一句話推薦理由（為何合併財報附表有被投資公司）"}}
  ]
}}"""
    else:
        # 沒有骨架地圖（fallback）：原本的獨立邏輯
        prompt = f"""你是台灣 PE 投資分析師助理。
用戶想研究「{track_name}」賽道的未上市隱形冠軍。
賽道關鍵字：{', '.join(keywords)}

任務：列出最適合作為文件輸入來源的台灣上市/上櫃公司。

【軌道一：年報上傳選擇標準】
- 在此賽道有大量採購行為，採購結構集中
- 嚴格回傳 5 筆，依揭露可能性由高到低排序

【軌道二：財報附表九選擇標準】
- 有已知創投投資組合或策略持股
- 嚴格回傳 5 筆

請只回傳 JSON，不要有任何其他文字：
{{
  "track1": [
    {{"company_name": "公司名", "ticker": "代號", "reason": "一句話推薦理由"}}
  ],
  "track2": [
    {{"company_name": "公司名", "ticker": "代號", "reason": "一句話推薦理由"}}
  ]
}}"""

    raw = gemini_text(prompt)
    data = json.loads(clean_json(raw))
    return BriefRecommendations(**data)

def generate_research_brief(
    track_name: str,
    track_config: dict,
    recommendations: BriefRecommendations,
    track3: dict = None,
) -> Path:
    if track3 is None:
        track3 = {}
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    keywords = track_config.get("search_keywords", [track_name])

    # 軌道一、二清單
    t1 = "\n".join(
        f"- [ ] **{c.company_name} ({c.ticker})** 年報 PDF\n      → {c.reason}"
        for c in recommendations.track1
    )
    t2 = "\n".join(
        f"- [ ] **{c.company_name} ({c.ticker})** 完整財務報告 PDF\n      → {c.reason}"
        for c in recommendations.track2
    )

    brief = f"""# 研究簡報：{track_name}
生成時間：{date_str}
搜尋關鍵字：{', '.join(keywords)}

---

## 📥 軌道一｜建議上傳年報
> Layer 2/3 公司，10% 條款強制揭露未上市供應商
> **請將 PDF 存入 `raw_inputs/`**

{t1}

---

## 📊 軌道二｜建議上傳財報附表九
> 找大廠創投持股的未上市新創
> **請將 PDF 存入 `raw_inputs/`**

{t2}

---

## 🗒 發現公司紀錄
> 上傳年報後自動填入，TIIP 補助資訊自動標記
"""

    safe = track_name.replace("/", "_").replace(" ", "_")
    date_short = datetime.now().strftime("%Y%m%d")
    path = VAULT_DIR / f"研究簡報_{safe}_{date_short}.md"
    path.write_text(brief, encoding="utf-8")
    return path


# ─── 文件處理（Watchdog 核心）────────────────────────────────────
EXTRACT_PROMPT = """你是一個極度嚴謹的私募股權投資（PE）數據審計 Agent。
從這份文件中，提取供應鏈相關企業（包含上市、上櫃、興櫃、未上市，全部納入）。

【目標範圍】
✅ 保留：所有被點名的供應商、合作廠商、被投資公司
✅ 包含：台股上市（TWSE）、上櫃（OTC）、興櫃、未上市公司
✅ 包含：外國公司（若在文件中明確點名）
— 上市狀態由後端系統自動判斷，Gemini 不需要過濾

【年報任務（Annual_Report / CSR_Report）】
✅ 提取目標——以下任一段落出現的供應商公司名稱：
  主要供應商 / 主要進貨廠商 / 關鍵供應商 / 重要供應商
  主要原料之供應狀況 / 原料供應來源 / 原物料採購 / 採購管理
  供應鏈管理 / 供應商管理 / 採購來源 / 進料廠商
  （章節名稱不限，凡列出供應公司名稱的表格或段落皆納入）

❌ 明確跳過——以下段落即使出現公司名稱也不提取：
  同業廠商 / 競爭對手 / 競爭產品 / 競爭分析 / 市場競爭
  主要客戶 / 重要客戶 / 客戶名單 / 銷售對象
  法律訴訟 / 重大契約糾紛 / 訴訟事件
  股東名單 / 董監事 / 關係人交易（非供應關係）
  子公司清單 / 轉投資事業一覽 / 被投資公司一覽 / 轉投資概況（轉投資資訊由財報附表九覆蓋，年報不重複提取）
  永續報告 / 溫室氣體盤查 / ESG / 碳排放 / 環境管理 / 供應鏈永續（此類段落揭露的通常是驗證機構、顧問公司，非供應商）

❌ 以下類型公司不論在何段落出現，一律不提取：
  金融機構：銀行、證券商、保險公司、票券公司、投信、投顧（如元大證券、國泰銀行、富邦金等）
  會計師事務所 / 法律事務所 / 律師事務所 / 建築師事務所
  公關公司 / 廣告代理商
  營造工程 / 建築設計 / 土木工程 / 工程顧問（廠房施工類，非持續性供應關係）

不需要採購佔比，有公司名稱即可提取。

【嚴格指令】
1. 只准提取黑字白紙寫出來的事實，嚴禁推論
2. unlisted_evidence 填入文件中出現該公司的原文依據（無則填「文件直接點名」）
3. 若無任何供應商資訊，returned_entities 回傳空陣列
4. PDF 輸入必須提供實際頁碼
5. 【匿名供應商處理】若主要供應商欄位以「甲公司」「乙公司」「丙公司」「其他」等匿名方式呈現，代表文件未揭露真實供應商名稱。此時必須直接回傳空陣列，絕對不可改去股東名冊、法人股東、轉投資事業、關係企業等其他段落搜尋替代資料。
6. 【嚴禁跨段落替補】若供應鏈段落找不到具名廠商，不得以任何理由在其他段落（股東、法人股東、投資人、被投資公司、關係人）萃取資料。寧可回傳空陣列，不可回傳非供應商的公司名稱。

7. `relation_category` 只允許填入以下三種值：`供應商`、`原料廠商`、`合作廠商`。若無法歸入這三類（例如股東、被投資公司、客戶、競爭對手），一律不提取此公司。
8. `source_section` 必須填入該公司出現的段落標題原文（例如「主要供應商資料」「原料供應狀況」），讓人可以回溯確認。

請只回傳以下 JSON，不要有任何其他文字：
{
  "source_company": "提供此文件的公司名稱（從文件判斷）",
  "track_name": "最符合的賽道名稱（從文件內容判斷）",
  "discovered_entities": [
    {
      "entity_name": "公司名稱",
      "business_description": "一句話說明此公司核心業務（20字以內）；必須來自文件明確描述，不可根據公司名稱或上下文推論；文件未明確描述則填「業務不明」",
      "source_type": "Annual_Report",
      "relation_category": "供應商 | 原料廠商 | 合作廠商（三擇一）",
      "source_section": "該公司出現的段落標題（原文）",
      "evidence_quote": "原文引用（100% 複製）",
      "page_number": 0,
      "context_relation": "關係描述",
      "unlisted_evidence": "未上市依據原文",
      "confidence": "high"
    }
  ]
}"""

EXTRACT_PROMPT_T2 = """你是一個私募股權投資（PE）數據分析 Agent，專門從合併財務報告中提取被投資公司名單。

【任務】
從這份合併財務報告中，找到被投資公司相關附表（常見為附表六、附表七或附表九），逐行提取所有被投資公司。
這是結構化資料提取任務，要求完整性，不是摘要。

【提取範圍】
✅ 提取被投資公司附表中每一行的被投資公司（無論上市、上櫃、興櫃、未上市）
✅ 包含台灣、日本境內有實際生產或研發業務的子公司、關聯公司（日本隱形冠軍具 PE 投資價值）

【排除範圍】
❌ 海外純控股公司：名稱含 Holdings、Corp.、Inc.、LLC、S.A.、GmbH、BV，或設立於 Cayman、BVI、Delaware、Ireland、Netherlands
❌ 行政管理性質：名稱含「管理顧問」「不動產」「物業」「資產管理」
❌ 純投資控股：業務描述含「控股」或「投資」字眼者，一律排除。即使附帶其他業務描述（如「投資控股及管理服務」），只要含有「控股」「投資」字眼，仍視為控股公司予以排除，不得保留。
❌ 與本公司主體業務完全無關的多角化投資（如餐飲、旅遊、零售、建設）

【嚴格指令】
1. 【資料來源限制】只允許從被投資公司相關附表（附表六、附表七、附表九或同性質附表）提取資料。其他財報科目一律不納入，即使該處有被投資公司名稱——包含但不限於：按公允價值衡量之金融資產、備供出售金融資產、應收帳款附表、備註揭露、重要會計政策說明。
2. 只提取被投資公司附表中明確列出的公司，不推論
3. business_description 填一句話說明核心業務；若文件未描述則填「業務不明」
4. context_relation 必須填入持股比例（如有）
5. evidence_quote 填原文中該公司的列示文字
6. 若找不到被投資公司相關附表，returned_entities 回傳空陣列
7. 【關鍵】持股比例不論高低（1%~100% 皆納入）一律提取，嚴禁因持股比例低（如5%、10%、11%）而跳過任何一行
8. 附表中同一投資公司名稱底下可能有多行被投資公司，每一行都必須單獨提取，不得只取第一行
9. 【多層結構】附表的「投資公司名稱」欄可能是中間控股公司（如開曼、BVI 實體），不代表「被投資公司名稱」欄的公司要被排除。判斷是否提取只看「被投資公司名稱」欄的業務與地區，與中間投資公司無關。日本境內的製造或銷售公司（如株式会社、有限会社）必須納入。
10. 【附表六層疊格式】部分公司的附表六採用「投資公司名稱 → 被投資公司名稱」兩欄格式，且投資公司欄會交替出現本公司、子公司（如崇智、崇盛、敏盛科技等）。每當「投資公司名稱」欄出現新公司名稱，代表該區塊是那家中間公司的投資清單。無論投資公司欄是本公司還是子公司，「被投資公司名稱」欄的所有台灣及日本實體都必須逐行提取，不可因投資公司欄切換而停止讀取。

9. `relation_category` 只允許填入以下三種值：`子公司`、`關聯企業`、`被投資公司`。依附表揭露的實際關係填寫，不可自行推論。
10. `source_section` 填入該公司出現的附表名稱原文（例如「附表六」「附表七」「附表九」，依文件實際編號填寫）。

請只回傳以下 JSON，不要有任何其他文字：
{
  "source_company": "本份財報的公司名稱（從文件判斷）",
  "track_name": "最符合的產業賽道名稱",
  "discovered_entities": [
    {
      "entity_name": "公司名稱",
      "business_description": "核心業務一句話（20字以內）；必須來自文件明確描述，不可推論；文件未描述則填「業務不明」",
      "source_type": "Financial_Statement",
      "relation_category": "子公司 | 關聯企業 | 被投資公司（三擇一）",
      "source_section": "附表九（或附表六）",
      "evidence_quote": "附表六或附表九原文列示文字",
      "page_number": 0,
      "context_relation": "持股比例或關係描述",
      "unlisted_evidence": "文件直接點名",
      "confidence": "high"
    }
  ]
}"""


def detect_source_type(file_path: Path) -> str:
    name = file_path.name.lower()
    if any(k in name for k in ["csr", "永續", "esg", "sustainability"]):
        return "CSR_Report"
    if any(k in name for k in ["financial", "財務", "fs_", "合併"]):
        return "Financial_Statement"
    return "Annual_Report"

# ─── PDF 全文萃取 ────────────────────────────────────────────────

def _extract_full_text(pdf_path: Path) -> str:
    """
    用 pdfplumber 抽取整份 PDF 的文字，含頁碼標記。
    正式上市/上櫃公司年報財報均為文字型 PDF，無需裁切或 fallback。
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[第{i+1}頁]\n{text}")
    log.info(f"PDF 全文萃取：{pdf_path.name}，共 {total} 頁，有效頁 {len(pages)} 頁")
    return "\n\n".join(pages)


def claude_extract(text: str, prompt: str, retries: int = 5) -> str:
    """用 Claude Sonnet 做文字萃取。"""
    full_prompt = (
        f"{prompt}\n\n"
        "以下是從文件中萃取的相關頁面內容（含頁碼標記）：\n\n"
        f"{text}"
    )
    for attempt in range(retries):
        try:
            resp = claude_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4096,
                messages=[{"role": "user", "content": full_prompt}],
            )
            return resp.content[0].text
        except Exception as e:
            err = str(e)
            is_rate_limit = "429" in err or "rate_limit" in err
            is_overload   = "529" in err or "overloaded" in err
            if attempt < retries - 1 and (is_rate_limit or is_overload):
                # rate limit：等 70s（分鐘限制 reset）；overload：等 30s
                wait = 70 if is_rate_limit else 30
                log.warning(f"Claude {'rate limit' if is_rate_limit else '過載'}，等 {wait}s 後重試（第{attempt+1}次）")
                time.sleep(wait)
            else:
                raise


def _run_extraction(
    file_path: Path,
    prompt: str,
    source_type: str = None,
) -> "TrackTreePayload | None":
    """
    單次萃取：
    - PDF → pdfplumber 抽全文（文字型 PDF），送 Claude Haiku
    - txt/md → 直接送 Claude Haiku
    回傳 TrackTreePayload 或 None。
    """
    try:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            # 原生 PDF 上傳：Gemini 自行讀取版面與表格，比 pdfplumber 文字更準確且 token 更省
            raw = gemini_pdf(file_path, prompt)
        elif suffix in [".txt", ".md"]:
            content = file_path.read_text(encoding="utf-8")
            full_prompt = (
                f"{prompt}\n\n"
                "以下是文件內容：\n\n"
                f"{content}"
            )
            raw = gemini_text(full_prompt)
        else:
            return None

        data = _safe_json_parse(clean_json(raw))
        if data is None:
            raise ValueError("JSON 解析失敗，clean_json 後仍無法解析")
        # 正規化 source_type 大小寫（模型偶爾輸出 Financial_statement 等變體）
        _ST_MAP = {
            "annual_report": "Annual_Report",
            "csr_report": "CSR_Report",
            "financial_statement": "Financial_Statement",
            "gov_grant": "Gov_Grant",
            "exhibition": "Exhibition",
            "job_posting": "Job_Posting",
        }
        for e in data.get("discovered_entities", []):
            st = e.get("source_type", "")
            e["source_type"] = _ST_MAP.get(st.lower(), st)
        return TrackTreePayload(**data)
    except Exception as e:
        log.warning(f"萃取失敗（單次）：{e}")
        return None


def _merge_payloads(p1: "TrackTreePayload", p2: "TrackTreePayload | None") -> "TrackTreePayload":
    """合併兩次萃取結果，以 entity_name 去重，p1 優先"""
    if p2 is None:
        return p1
    seen = {e.entity_name for e in p1.discovered_entities}
    merged = list(p1.discovered_entities)
    added = 0
    for e in p2.discovered_entities:
        if e.entity_name not in seen:
            seen.add(e.entity_name)
            merged.append(e)
            added += 1
    if added:
        log.info(f"第二次萃取補充 {added} 家公司")
    return TrackTreePayload(
        source_company=p1.source_company,
        track_name=p1.track_name,
        discovered_entities=merged,
    )


def process_file(
    file_path: Path,
    tracks: dict,
    source_type: str = None,
    target_track_name: str = None,   # 使用者在 UI 選定的賽道，優先於 Gemini 自判
) -> str | None:
    log.info(f"開始處理：{file_path.name}")

    # T2 財報用獨立 prompt，T1 年報用原 prompt
    if source_type == "Financial_Statement":
        prompt = EXTRACT_PROMPT_T2
    else:
        prompt = EXTRACT_PROMPT
        if source_type:
            hint = (
                f"\n【文件類型（已確認）】此文件為 {source_type}，"
                f"discovered_entities 中每筆的 source_type 請填入此值。\n"
            )
            prompt = hint + prompt

    # 萃取（T1/T2 皆單次，頁面已精準裁切，不需重複跑）
    payload = _run_extraction(file_path, prompt, source_type=source_type)
    if payload is None:
        log.error(f"處理失敗：{file_path.name}")
        return None, 0

    # 使用者明確選定的賽道覆蓋模型自判的 track_name
    if target_track_name:
        if payload.track_name != target_track_name:
            log.info(f"track_name 覆蓋：模型='{payload.track_name}' → UI='{target_track_name}'")
        payload = TrackTreePayload(
            source_company=payload.source_company,
            track_name=target_track_name,
            discovered_entities=payload.discovered_entities,
        )

    if not payload.discovered_entities:
        log.info(f"未發現符合條件的公司：{file_path.name}")
        return payload.source_company, 0

    # ── 後處理過濾：確保 LLM 未遵守的排除規則在此強制執行 ────────────
    _HOLDING_KEYWORDS = ["控股", "Holdings", "Investment", "Holding"]  # 不含「投資」：正常 operating company 描述也常出現此字，會誤殺
    _OFFSHORE_REGIONS = ["Cayman", "BVI", "Delaware", "Ireland", "Netherlands",
                         "開曼", "英屬維京"]
    _ADMIN_KEYWORDS   = ["管理顧問", "不動產", "物業管理", "資產管理"]
    # 外國法律形式後綴
    _FOREIGN_SUFFIXES = ["Co., Ltd.", "Co.,Ltd.", "Pte. Ltd.", "Pte Ltd",
                         "Private Limited", "Inc.", "LLC", "GmbH", "S.A.", "B.V."]
    # 括號外地名常見前綴（限最明確的，避免誤傷台灣公司）
    _FOREIGN_PREFIXES = ["香港", "澳門"]
    # 純流通業務關鍵字
    _DISTRIBUTION_KW  = ["銷售", "行銷", "貿易", "distribution", "trading", "sales"]
    _MFG_KW           = ["製造", "生產", "研發", "開發", "加工", "manufacturing", "production"]

    # 明確已知的境外地名（括號形式），精準列舉，不用寬鬆 regex 避免誤傷台灣公司
    _FOREIGN_BRACKETS = [
        "香港", "澳門", "新加坡", "美國", "英國", "德國", "法國", "荷蘭", "愛爾蘭",
        "日本", "韓國", "越南", "泰國", "馬來西亞", "印尼", "菲律賓", "印度",
        "中國大陸", "北京", "上海", "深圳", "廣東", "廈門", "成都", "蘇州",
        "UK", "USA", "Japan", "Korea", "Vietnam", "Thailand", "Germany",
    ]

    def _is_overseas(name: str) -> bool:
        """偵測非台灣實體：外國法律形式後綴、明確境外地名前綴或括號標注"""
        if any(s in name for s in _FOREIGN_SUFFIXES):
            return True
        if any(name.startswith(p) for p in _FOREIGN_PREFIXES):
            return True
        # 括號內為已知境外地名（精準比對，避免（上市）（未上市）（興櫃）被誤判）
        bracket_content = re.findall(r'[（(]([^）)]+)[）)]', name)
        if any(loc in bc for bc in bracket_content for loc in _FOREIGN_BRACKETS):
            return True
        return False

    def _is_pure_distribution(biz: str) -> bool:
        """純流通性質：含銷售/行銷字眼，且無製造/研發字眼"""
        return (any(kw in biz for kw in _DISTRIBUTION_KW)
                and not any(kw in biz for kw in _MFG_KW))

    def _should_exclude(e) -> bool:
        biz  = e.business_description if hasattr(e, "business_description") else e.get("business_description", "")
        name = e.entity_name if hasattr(e, "entity_name") else e.get("entity_name", e.get("company_name", ""))
        # 業務描述含控股/投資字眼 → 排除
        if any(kw in biz for kw in _HOLDING_KEYWORDS):
            return True
        # 公司名稱含明確控股/投資字眼
        if any(kw in name for kw in ["控股", "Investment", "Holdings", "Holding"]):
            return True
        # 純離岸控股地 → 直接排除
        if any(r in name for r in _OFFSHORE_REGIONS):
            return True
        # 行政管理性質 → 排除
        if any(kw in biz for kw in _ADMIN_KEYWORDS):
            return True
        # 海外實體 + 純流通業務 → 排除
        if _is_overseas(name) and _is_pure_distribution(biz):
            return True
        return False

    before_count = len(payload.discovered_entities)
    filtered = [e for e in payload.discovered_entities if not _should_exclude(e)]
    removed  = before_count - len(filtered)
    if removed:
        removed_names = [(e.entity_name if hasattr(e, "entity_name") else e.get("entity_name", e.get("company_name","?"))) for e in payload.discovered_entities if _should_exclude(e)]
        log.info(f"後處理過濾移除 {removed} 筆控股/投資公司：{removed_names}")
        payload = TrackTreePayload(
            source_company=payload.source_company,
            track_name=payload.track_name,
            discovered_entities=filtered,
        )

    if not payload.discovered_entities:
        log.info(f"過濾後無剩餘公司：{file_path.name}")
        return payload.source_company, 0

    log.info(f"發現 {len(payload.discovered_entities)} 家公司（過濾前）← {file_path.name}")
    written = append_to_track_tree(payload, tracks, source_type=source_type, source_pdf=file_path.name)
    return payload.source_company, written

def manual_add_to_tree(
    entity_name: str,
    tree_file: Path,
    business_description: str = "",
    relation_category: str = "供應商",
    source_company: str = "",
) -> bool:
    """手動新增一筆公司到賽道樹狀圖。回傳是否成功。"""
    if not entity_name.strip() or not tree_file:
        return False
    TRACK_TREES_DIR.mkdir(parents=True, exist_ok=True)
    if not tree_file.exists():
        tree_file.write_text(
            f"# 賽道樹狀圖\n\n*由 Sector Radar 自動維護*\n\n"
            f"| 公司名 | 在做什麼 | 上市狀態 | 來源軌道 | 關係類型 | 關係對象 |\n"
            f"|--------|---------|---------|---------|---------|----------|\n",
            encoding="utf-8"
        )
    listing = get_listing_status(entity_name.strip())
    desc    = (business_description.strip() or "業務不明").replace("|", "｜")
    rel     = relation_category.strip() or "供應商"
    src     = source_company.strip()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    row = (
        f"\n<!-- {date_str} | 來源：手動新增 -->\n"
        f"| {entity_name.strip()} | {desc} | {listing} | 手動 | {rel} | {src} |\n"
    )
    with open(tree_file, "a", encoding="utf-8") as f:
        f.write(row)

    details_file = tree_file.with_name(tree_file.stem + "_details.json")
    existing = []
    if details_file.exists():
        try:
            existing = json.loads(details_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing.append({
        "entity_name":          entity_name.strip(),
        "business_description": desc,
        "listing_status":       listing,
        "track":                "手動",
        "evidence_quote":       "",
        "page_number":          0,
        "unlisted_evidence":    "",
        "source_company":       src,
        "source_type":          "Manual",
        "source_pdf":           "",
        "relation_category":    rel,
        "source_section":       "",
        "timestamp":            datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    details_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"手動新增：{entity_name.strip()} → {tree_file.name}")
    return True


def delete_manual_entry(entity_name: str, tree_file: Path) -> bool:
    """從 tree .md 和 _details.json 刪除一筆手動新增的公司。"""
    if not tree_file or not tree_file.exists():
        return False
    # 清 .md：移除包含該公司名稱且來源為「手動新增」的 header + row
    lines = tree_file.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines, skip_next, removed = [], False, False
    for line in lines:
        if "來源：手動新增" in line:
            # 檢查下一行是否是目標公司
            skip_next = True
            _pending_header = line
            continue
        if skip_next:
            skip_next = False
            if f"| {entity_name} " in line or f"| {entity_name.strip()} " in line:
                removed = True
                continue  # 跳過 header 和 row
            else:
                new_lines.append(_pending_header)  # 不是目標，保留 header
        new_lines.append(line)
    if removed:
        tree_file.write_text("".join(new_lines), encoding="utf-8")
    # 清 _details.json
    details_file = tree_file.with_name(tree_file.stem + "_details.json")
    if details_file.exists():
        try:
            records = json.loads(details_file.read_text(encoding="utf-8"))
            filtered = [r for r in records if not (
                r.get("entity_name") == entity_name and r.get("source_type") == "Manual"
            )]
            details_file.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return removed


def purge_source_from_tree(source_company: str, tree_file: Path) -> int:
    """
    從 tree .md 和 _details.json 中清除來自特定 source_company 的所有記錄。
    回傳清除的筆數（.md 行數）。
    """
    removed = 0

    # ── 清 .md ──────────────────────────────────────────────────────
    if tree_file.exists():
        lines = tree_file.read_text(encoding="utf-8").splitlines(keepends=True)
        new_lines = []
        skip_block = False
        for line in lines:
            # 區塊 header：<!-- date | 來源：公司名 -->
            if line.strip().startswith("<!--") and f"來源：{source_company}" in line:
                skip_block = True
                continue
            # 下一個區塊 header → 結束 skip
            if skip_block and line.strip().startswith("<!--"):
                skip_block = False
            if skip_block and line.strip().startswith("|") and not line.strip().startswith("|---"):
                removed += 1
                continue
            if not skip_block:
                new_lines.append(line)
        tree_file.write_text("".join(new_lines), encoding="utf-8")

    # ── 清 _details.json ─────────────────────────────────────────────
    details_file = tree_file.with_name(tree_file.stem + "_details.json")
    if details_file.exists():
        try:
            records = json.loads(details_file.read_text(encoding="utf-8"))
            filtered = [r for r in records if r.get("source_company") != source_company]
            details_file.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning(f"清除 _details.json 失敗：{e}")

    log.info(f"purge_source_from_tree：移除 {source_company} 共 {removed} 行")
    return removed


def append_to_track_tree(payload: TrackTreePayload, tracks: dict, source_type: str = None, source_pdf: str = ""):
    # 找對應賽道
    track_config = None
    for key, config in tracks.items():
        if (config["name"] == payload.track_name
                or any(kw in payload.track_name for kw in config.get("file_keywords", []))):
            track_config = config
            break

    if not track_config:
        # 自動建立動態設定，絕不 fallback 到其他賽道污染資料
        safe_name = (
            payload.track_name
            .replace("/", "_").replace("\\", "_")
            .replace(" ", "_").replace("　", "_")
            .strip("_")[:40]
        ) or "未分類"
        track_config = {
            "name":            payload.track_name,
            "search_keywords": [payload.track_name],
            "file_keywords":   [payload.track_name],
            "tree_file":       f"{safe_name}賽道.md",
        }
        log.warning(f"找不到賽道 '{payload.track_name}'，自動建立獨立 tree：{track_config['tree_file']}")

    tree_file = TRACK_TREES_DIR / track_config["tree_file"]
    TRACK_TREES_DIR.mkdir(parents=True, exist_ok=True)

    if not tree_file.exists():
        tree_file.write_text(
            f"# {track_config['name']} 賽道樹狀圖\n\n"
            f"*由 Sector Radar 自動維護，Append-Only*\n\n"
            f"| 公司名 | 在做什麼 | 上市狀態 | 來源軌道 | 關係類型 | 關係對象 |\n"
            f"|--------|---------|---------|---------|---------|----------|\n",
            encoding="utf-8"
        )

    # source_type → 軌道標籤
    def track_label(source_type: str) -> str:
        if source_type == "Financial_Statement":
            return "T2"
        elif source_type == "Gov_Grant":
            return "T3"
        else:
            return "T1"

    # source_type → 關係類型
    def relation_type(source_type: str) -> str:
        if source_type == "Financial_Statement":
            return "被投資公司"
        elif source_type == "Gov_Grant":
            return "補助對象"
        else:
            return "供應商"

    # ── 後處理過濾 ──────────────────────────────────────────────────

    # source company 正規化：只去法律後綴，保留完整品牌名
    _src_normalized = (
        payload.source_company
        .replace("股份有限公司", "").replace("有限公司", "").strip()
    )

    def _should_exclude(entity_name: str) -> bool:
        n = entity_name.strip()
        # 海外／外國公司：T1 + T2 都過濾
        if is_foreign_company(n):
            return True
        # 自我參照過濾：
        # ① 完全相符（本身）
        # ② entity 名稱是 source 名稱的子集（如 source=日月光投資控股，entity=日月光）
        #    → 代表 entity 是集團核心業務實體，不是獨立隱形冠軍
        # ③ 不過濾「source 是 entity 的子集」（如 entity=日月光半導體製造，source=日月光），
        #    因為子品牌仍可能是有價值的獨立標的
        n_normalized = n.replace("股份有限公司", "").replace("有限公司", "").strip()
        if _src_normalized and (
            n_normalized == _src_normalized          # ① 完全相符
            or (len(n_normalized) >= 2              # ② entity 是 source 的子集
                and n_normalized in _src_normalized)
        ):
            return True
        return False

    entities = [e for e in payload.discovered_entities if not _should_exclude(e.entity_name)]
    excluded = len(payload.discovered_entities) - len(entities)
    if excluded:
        log.info(f"後處理過濾：移除 {excluded} 筆（海外子公司或自家集團）")

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    header_block = f"\n<!-- {date_str} | 來源：{payload.source_company} -->\n"
    rows = ""

    for e in entities:
        listing = get_listing_status(e.entity_name)
        # 用外層傳入的 source_type（UI 上傳軌道）優先；Gemini 自判僅備用
        effective_type = source_type or e.source_type
        track   = track_label(effective_type)
        rel     = relation_type(effective_type)
        desc    = e.business_description.replace("|", "｜")

        rows += (
            f"| {e.entity_name} "
            f"| {desc} "
            f"| {listing} "
            f"| {track} "
            f"| {rel} "
            f"| {payload.source_company} |\n"
        )

    with open(tree_file, "a", encoding="utf-8") as f:
        f.write(header_block + rows)

    # 同步寫入詳細資料 JSON（供 UI 詳情卡片使用）
    details_file = tree_file.with_name(tree_file.stem + "_details.json")
    existing = []
    if details_file.exists():
        try:
            existing = json.loads(details_file.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    effective_type_for_details = source_type  # 外層傳入的軌道類型
    for e in payload.discovered_entities:
        _etype = effective_type_for_details or e.source_type
        existing.append({
            "entity_name":          e.entity_name,
            "business_description": e.business_description,
            "listing_status":       get_listing_status(e.entity_name),
            "track":                track_label(_etype),
            "evidence_quote":       e.evidence_quote,
            "page_number":          e.page_number,
            "unlisted_evidence":    e.unlisted_evidence,
            "source_company":       payload.source_company,
            "source_type":          _etype,
            "source_pdf":           source_pdf,
            "relation_category":    e.relation_category,
            "source_section":       e.source_section,
            "timestamp":            datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
    details_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 已寫入賽道樹狀圖：{tree_file.name}（{len(entities)} 家公司）")
    log.info(f"寫入完成：{tree_file.name}")
    return len(entities)


# ─── Watchdog Handler ────────────────────────────────────────────
class LibrarianHandler(FileSystemEventHandler):
    def __init__(self, tracks: dict, processed: set):
        self.tracks = tracks
        self.processed = processed
        self._timers: dict = {}

    def on_created(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def _schedule(self, path: str):
        if path in self._timers:
            self._timers[path].cancel()
        t = threading.Timer(1.5, self._handle, args=[path])
        self._timers[path] = t
        t.start()

    def _handle(self, path: str):
        fp = Path(path)
        if str(fp) in self.processed:
            return
        if not fp.exists():
            return
        if fp.suffix.lower() not in [".pdf", ".txt"]:
            return
        if fp.name.startswith("_"):
            return

        try:
            process_file(fp, self.tracks)
            self.processed.add(str(fp))
            save_processed(self.processed)
        except Exception as e:
            log.error(f"處理異常：{fp.name}：{e}")


# ─── 主指令 ──────────────────────────────────────────────────────
def cmd_new_track(track_name: str):
    tracks = load_tracks()

    # 找匹配的賽道設定
    track_config = None
    for config in tracks.values():
        if config["name"] == track_name or track_name in config["name"]:
            track_config = config
            break
    if not track_config:
        track_config = {
            "name": track_name,
            "search_keywords": [track_name],
            "file_keywords": [track_name],
            "tree_file": f"{track_name}賽道.md"
        }
        log.info(f"賽道 '{track_name}' 未在 tracks.yaml 定義，使用動態設定")

    keywords = track_config.get("search_keywords", [track_name])

    print(f"\n🔍 開始建立「{track_name}」研究簡報...\n")

    # Step 1：Gemini 生成公司推薦
    print("⏳ [1/3] Gemini 分析 Layer 2/3 推薦公司...")
    try:
        recs = generate_recommendations(track_name, keywords)
    except Exception as e:
        log.error(f"推薦生成失敗：{e}")
        return

    # Step 2：軌道三爬取
    print("⏳ [2/3] 軌道三搜尋中... (TIIP / SBIR)")
    track3 = crawl_track3(keywords)
    tiip_n = len(track3.get("tiip", []))
    sbir_n  = len(track3.get("sbir", []))

    # Step 3：生成研究簡報
    print("⏳ [3/3] 生成研究簡報...")
    brief_path = generate_research_brief(track_name, track_config, recs, track3)

    print(f"\n✅ 研究簡報：{brief_path}")
    print(f"✅ 軌道三：TIIP {tiip_n} 家 / SBIR {sbir_n} 家")
    print(f"\n📋 下一步：")
    print(f"   1. 在 Obsidian 開啟研究簡報查看推薦清單")
    print(f"   2. 下載推薦公司的年報/財報 PDF")
    print(f"   3. 存入：{RAW_INPUTS_DIR}")
    print(f"   4. 執行 python librarian.py --watch 啟動監控\n")

def cmd_watch():
    tracks    = load_tracks()
    processed = load_processed()
    RAW_INPUTS_DIR.mkdir(parents=True, exist_ok=True)

    handler  = LibrarianHandler(tracks, processed)
    observer = Observer()
    observer.schedule(handler, str(RAW_INPUTS_DIR), recursive=False)
    observer.start()

    print(f"\n👁  Watchdog 啟動，監控中：{RAW_INPUTS_DIR}")
    print(f"    將 PDF 或 TXT 存入此資料夾即可自動處理")
    print(f"    按 Ctrl+C 停止\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n⏹  Watchdog 已停止")
    observer.join()


# ─── Entry Point ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="EMS Librarian — PE KM Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""範例：
  python librarian.py --new-track "半導體先進封裝"
  python librarian.py --watch
  python librarian.py --new-track "被動元件" --watch"""
    )
    parser.add_argument("--new-track",      metavar="TRACK_NAME", help="建立新賽道研究簡報")
    parser.add_argument("--watch",          action="store_true",  help="啟動 Watchdog 監控 raw_inputs/")
    parser.add_argument("--update-cache",   action="store_true",  help="強制更新 TIIP/SBIR 本機 cache（完整爬取）")
    parser.add_argument("--update-listed",  action="store_true",  help="下載 TWSE/OTC/興櫃 公司名單（MVP 一次性執行）")
    args = parser.parse_args()

    if args.update_listed:
        build_listed_companies_cache()

    if args.update_cache:
        build_tiip_cache(max_pages=113)
        build_sbir_cache()
        print("✅ Cache 更新完成")

    if args.new_track:
        cmd_new_track(args.new_track)

    if args.watch:
        cmd_watch()

    if not any([args.new_track, args.watch, args.update_cache, args.update_listed]):
        parser.print_help()

if __name__ == "__main__":
    main()
