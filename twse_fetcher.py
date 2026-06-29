#!/usr/bin/env python3
"""
TWSE/OTC Company Fetcher
抓取台灣上市（TWSE）與上櫃（OTC/TPEX）公司清單，含產業分類。
結果存到 data/twse_companies.json，供骨架地圖 prompt 使用。

Usage:
  python twse_fetcher.py          # 抓取並存檔（覆蓋舊版）
  python twse_fetcher.py --stats  # 顯示產業別統計
"""

import argparse
import json
import sys
from pathlib import Path
from collections import Counter

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR   = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "data" / "twse_companies.json"

TWSE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
OTC_URL  = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"


def fetch_twse() -> list[dict]:
    """抓上市公司（TWSE）"""
    print("  抓取 TWSE 上市公司...")
    r = requests.get(TWSE_URL, timeout=30, verify=False)
    r.raise_for_status()
    raw = r.json()
    results = []
    for item in raw:
        name = item.get("公司名稱", "").strip()
        short = item.get("公司簡稱", "").strip()
        code = item.get("公司代號", "").strip()
        industry = item.get("產業別", "").strip()
        if not name or not code:
            continue
        results.append({
            "name":       name,
            "short_name": short or name,
            "code":       code,
            "market":     "上市",
            "industry":   industry,
        })
    print(f"  → {len(results)} 家上市公司")
    return results


def fetch_otc() -> list[dict]:
    """抓上櫃公司（OTC/TPEX）"""
    print("  抓取 OTC 上櫃公司...")
    r = requests.get(OTC_URL, timeout=30, verify=False)
    r.raise_for_status()
    raw = r.json()
    results = []
    for item in raw:
        name = item.get("CompanyName", "").strip()
        short = item.get("CompanyAbbreviation", "").strip()
        code = item.get("SecuritiesCompanyCode", "").strip()
        industry = item.get("SecuritiesIndustryCode", "").strip()
        if not name or not code:
            continue
        results.append({
            "name":       name,
            "short_name": short or name,
            "code":       code,
            "market":     "上櫃",
            "industry":   industry,
        })
    print(f"  → {len(results)} 家上櫃公司")
    return results


def build_database() -> dict:
    """合併上市+上櫃，以公司名稱為 key 建立資料庫"""
    all_companies = fetch_twse() + fetch_otc()

    # 去重（以 code 為準，公司名可能有細微差異）
    seen_codes = set()
    db = {}
    for c in all_companies:
        if c["code"] in seen_codes:
            continue
        seen_codes.add(c["code"])
        db[c["name"]] = {
            "code":       c["code"],
            "short_name": c["short_name"],
            "market":     c["market"],
            "industry":   c["industry"],
        }

    print(f"\n  合併後共 {len(db)} 家公司（已去重）")
    return db


def get_tech_companies(db: dict) -> list[dict]:
    """
    取得電子/科技相關公司（股票代號 2000-6999）。
    回傳 list of {"name": 全稱, "short_name": 簡稱, "code": 代號}
    """
    result = []
    for name, info in db.items():
        code = info.get("code", "")
        if code.isdigit() and 2000 <= int(code) <= 6999:
            result.append({
                "name":       name,
                "short_name": info.get("short_name", name),
                "code":       code,
            })
    result.sort(key=lambda x: x["code"])
    return result


def print_stats(db: dict):
    """顯示產業別分佈"""
    industries = Counter(v["industry"] for v in db.values())
    print(f"\n{'產業別':<30} {'家數':>6}")
    print("-" * 38)
    for ind, cnt in sorted(industries.items(), key=lambda x: -x[1]):
        print(f"{ind:<30} {cnt:>6}")


def filter_by_industries(db: dict, industry_keywords: list[str]) -> list[str]:
    """
    根據產業關鍵字列表篩選公司名稱。
    例：filter_by_industries(db, ["半導體", "電子零組件", "光電"])
    回傳符合條件的公司名稱清單。
    """
    result = []
    for name, info in db.items():
        ind = info.get("industry", "")
        if any(kw in ind for kw in industry_keywords):
            result.append(name)
    return result


def load_db() -> dict:
    """從本地 JSON 載入資料庫（供其他模組 import 使用）"""
    if not OUTPUT_FILE.exists():
        raise FileNotFoundError(
            f"找不到 {OUTPUT_FILE}，請先執行 python twse_fetcher.py"
        )
    return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", action="store_true", help="顯示產業別統計")
    args = parser.parse_args()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("▶ 開始抓取 TWSE/OTC 公司資料...")
    db = build_database()

    OUTPUT_FILE.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n✅ 已存到 {OUTPUT_FILE}")

    if args.stats:
        print_stats(db)


if __name__ == "__main__":
    main()
