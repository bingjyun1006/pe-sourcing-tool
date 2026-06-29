# EMS — 標的管理模組規格書（Fact Vault）
## SPEC_B v1.0
**建立日期**：2026-05-29  
**負責人**：Brandon Chen  
**狀態**：已對齊，待開發  
**對應模組**：模組 2 — 防禦端（The Fact Vault）

---

## 一、模組定位

已識別的標的公司建立立案 Wiki、自動填入基本資料、沉澱機構知識，並以 Pipeline Dashboard 管理投研進度。

### 鐵律
- **只碰 100% 事實**：嚴禁任何推論、猜測、關聯性連連看
- **Append-Only**：知識只增不改，保留完整歷史佐證鏈
- **本機優先**：所有資料存於本機，無雲端資料庫

---

## 二、Stage 分類系統

每家公司在 YAML Frontmatter 標記所處投研階段，系統自動彙整各 Stage 的公司清單：

| Stage | 說明 |
|-------|------|
| `pipeline` | 初步觀察，尚未正式研究 |
| `researching` | 深度調研中 |
| `ic_ready` | 資料備齊，準備提交投資委員會 |
| `portfolio` | 已投資，進入投後管理 |
| `exited` | 已退出 |

---

## 三、Pipeline Dashboard（`_index.md`）

`02_Fact_Vault/_index.md` 為模組首頁，以 Obsidian **Dataview** 外掛自動產生動態 Pipeline 視圖：

- **總覽區**：各 Stage 公司數量一覽
- **清單區**：點擊 Stage 展開，顯示該 Stage 所有公司

**公司清單欄位：**

| 欄位 | 來源 YAML 欄位 |
|------|---------------|
| 公司名稱（WikiLink，點擊進入 profile）| 檔案名稱 |
| 賽道 | `track` |
| 文件數 | `doc_count` |
| 發現日期 | `created` |
| 最後更新 | `last_doc_update` |

Dataview 動態更新，新增公司或 stage 變更後自動反映，無需手動維護清單。

---

## 四、公司立案入口

### 入口 A：從 Fact Hunter 升級

1. 分析師點開 `[[X精密 (未上市)]]`，在 YAML Frontmatter 改 `status: "vault"` 並設定初始 `stage: "pipeline"`
2. Watchdog 偵測到狀態變更，自動執行：
   - 將檔案搬移至 `02_Fact_Vault/entities/`
   - 將歷史佐證鏈格式化寫入 Profile
   - 觸發商工登記自動查詢，填入基本資料

### 入口 B：手動建立

1. 分析師直接在 `02_Fact_Vault/entities/` 新增公司 Markdown 檔
2. 在 YAML Frontmatter 設定 `status: "vault"` + `stage` + 基本資訊
3. 上傳已有資料至系統，AI 解析後建成知識基底
4. 與入口 A 共用同一套模板與後續流程

---

## 五、文件自動解析 → Profile Insights（核心賣點）

**觸發方式**：分析師將任何公司相關文件（訪談逐字稿、新聞、研究報告、財報、會議紀錄）丟入該公司的 `documents/` 資料夾，Watchdog 自動偵測並處理。

**AI 任務**：
- 讀取文件全文，針對「這家公司」萃取關鍵 insights
- 每條 insight 精確標記來源：檔案名稱 + 頁碼 / 段落
- 自動 Append 至 Profile 的「AI 綜整摘要」區塊

**三個品質機制**：

| 機制 | 說明 |
|------|------|
| **去重** | 相同 insight 出現在多份文件時合併，並列出所有來源 |
| **衝突標記** | 矛盾資訊標示 `⚠️ 衝突` 並並列兩個來源，不自動選邊 |
| **來源追溯** | 每條 insight 可點回原始文件段落，不憑空產生 |

---

## 六、Pre-DD 黃頁自動填入（商工登記）

| 欄位 | 來源 | 說明 |
|------|------|------|
| 負責人 | 經濟部商工登記（自動爬取） | 單一命中直接填入；多筆結果標示警示 |
| 資本額 | 經濟部商工登記（自動爬取） | 同上 |
| 設立日期 | 經濟部商工登記（自動爬取） | 同上 |
| 員工規模 | 104 公司頁面 | 自動抓取 |
| 主力產品 | 公司官網 / 104 | 自動抓取 |
| 實際營收 | — | 未上市不公開，手動補充 |
| 股東結構 | — | 私密資訊，手動補充 |
| KP 聯絡人 | — | 需人脈，手動補充 |

**自動填入行為規則**：
- 單一精確命中 → 自動填入 + 附參考連結
- 多筆結果 → 填入第一筆 + `⚠️ 查詢到多筆結果，請人工確認` 警示 + 附參考連結
- 查無結果 → 欄位留空 + `⚠️ 查無資料` + 附參考連結

> **參考連結永遠附上**，供人工 double-check，不可省略。  
> **手動修改**：Obsidian 原生可直接編輯任何欄位，修改後欄位標記「（已手動更新）」

---

## 七、機構記憶時間軸

- 每次新增訪談紀錄、調研報告、會議紀錄，Append 至時間軸區塊
- 永不覆蓋，完整保留歷史

---

## 八、技術架構

```
分析師丟入公司文件
      ↓
entities/X精密/documents/ 資料夾
      ↓
librarian.py（Watchdog 自動監控）
      ↓
Gemini 1.5 Pro API（整本文件原生解讀）
      ↓
Pydantic 強制 JSON 格式校驗
      ↓
Append 至 X精密.md Profile（純 Markdown，本機存儲）
      ↓
Log 檔記錄（每次處理結果）
```

### 技術棧

| 元件 | 選型 | 理由 |
|------|------|------|
| AI 模型 | Gemini 1.5 Pro | 原生 PDF 解讀、2M Token、免費額度夠用 |
| 資料夾監控 | watchdog（Python）| 自動偵測新檔案，無需手動觸發 |
| 資料校驗 | Pydantic | 強制 JSON 格式，確保 100% 可解析 |
| 知識庫介面 | Obsidian Vault | KM 功能內建、Graph View 可視化、WikiLink、Dataview |
| 公司資料查詢 | 經濟部商工登記 API | 自動填入 Pre-DD 基本欄位 |

---

## 九、Pydantic 資料結構

```python
from pydantic import BaseModel, Field
from typing import List, Literal

class ProfileInsight(BaseModel):
    insight: str = Field(description="針對該公司的單一關鍵事實或洞察，100% 來自原文")
    source_file: str = Field(description="來源檔案名稱")
    source_location: str = Field(description="頁碼或段落描述，如 'P.42' 或 '第三段'")
    insight_type: Literal["business", "financial", "people", "product", "risk", "other"]
    conflict_flag: bool = Field(description="若此 insight 與已知資料有衝突則為 True")
    conflict_note: str = Field(default="", description="衝突說明，conflict_flag=True 時必填")

class ProfilePayload(BaseModel):
    company_id: str = Field(description="對應 YAML Frontmatter 的 id 欄位")
    source_file: str = Field(description="本次解析的文件檔名")
    insights: List[ProfileInsight]
```

---

## 十、目錄結構（本模組相關）

```
PE KM tool/
├── .env                          # GEMINI_API_KEY（不進 git）
├── librarian.py                  # 核心調度腳本
├── processing.log
└── Obsidian_Vault/
    └── 02_Fact_Vault/
        └── entities/
            ├── X精密/
            │   ├── X精密.md      # Profile 主頁（三區設計：AI 區 / 分析師區 / 歷史區）
            │   └── documents/    # 公司專屬文件（AI 做完整結構化萃取）
            │       └── _README.md
            └── _index.md         # Pipeline Dashboard（Dataview 動態產生）
```

---

## 十一、公司 Profile 頁面模板（entities/X精密/X精密.md）

Profile 頁面分為兩層：**濃縮摘要**（快速瀏覽）+ **詳細資料**（完整歷史）。

```markdown
---
id: "x_precision"
status: "vault"
stage: "researching"         # pipeline / researching / ic_ready / portfolio / exited
track: "semiconductor_packaging"
owner: "Brandon"
created: "2026-05-28"
source: "fact_hunter"        # fact_hunter / research_mode / manual
last_doc_update: "2026-05-28"
doc_count: 3
---

# X精密 (未上市)

<!-- ═══ AI 區（自動維護，請勿直接修改以下兩個區塊）══════════ -->

> [!summary] 🧠 AI 綜整摘要（每次新文件後重新生成）
> 資料來源：3 份文件｜最後更新：2026-05-28
>
> - 前三大電鍍設備供應商之一（來源：弘塑年報 2025 P.42）
> - 近期積極擴充 CoWoS 相關設備產線（來源：104 職缺 2025-03、訪談 2026-01）
> - ⚠️ **衝突**：資本額一說 5,000 萬（商工登記），一說近 1 億（訪談 2026-01），待確認

> [!tip] 分析師備註（AI 不會覆蓋此區，可自由填寫觀點與判斷）

---

> [!info]- 📁 文件列表（3 份）
> | 文件名稱 | 類型 | 上傳日期 | 解析狀態 |
> |---------|------|---------|---------|
> | 弘塑2025年報.pdf | 外部年報 | 2026-05-27 | ✅ 已解析 |
> | 20260115_專家訪談.txt | 公司專屬 | 2026-05-28 | ✅ 已解析 |
> | X精密_官網截圖.pdf | 公司專屬 | 2026-05-28 | ✅ 已解析 |

> [!info] 🌐 線上資訊快照（系統自動抓取，手動觸發「重新查詢」才更新）
> - **負責人**：王大明 🔗 [商工登記](https://findbiz.nat.gov.tw/...)
> - **資本額**：5,000 萬 🔗 [商工登記](...) ⚠️ 見衝突說明
> - **設立日期**：2015-03-15
> - **員工規模**：50–100 人 🔗 [104 公司頁](...)
> - **主力產品**：電鍍製程設備 🔗 [官網](...)
> - **近期新聞**：2025-11 電子時報，新產線擴充 🔗 [連結](...)

> [!note]- 🔍 Profile Insights（AI Append-Only，可刪除不需要的條目）
> - 【product】前三大電鍍設備供應商之一（弘塑年報 P.42）
> - 【business】2025 年與弘塑簽訂三年框架合作協議（弘塑年報 P.67）
> - 【financial】⚠️ 衝突：資本額 5,000 萬（商工登記）vs 近 1 億（訪談 2026-01 P.3）
> - （其餘 Insights 往下累積）

---

<!-- ═══ 分析師區（AI 永遠不碰）══════════════════════════════ -->

## 📝 Pre-DD 欄位

- **實際營收規模**：___
- **真實股東結構**：___
- **關鍵決策人 / 聯絡方式**：___
- **主要競爭對手**：___
- **私下觀察 / 訪談筆記**：

---

<!-- ═══ 歷史紀錄區（AI Append-Only，永不覆蓋）═══════════════ -->

> [!info] 📌 發現來源
> - 🔗 弘塑 2025 年報 第 42 頁：「前三大電鍍設備供應商之一」（原文）
> - 🔗 104 職缺（2025-03）：招募具台積電 CoWoS 經驗工程師（原文）

> [!summary]- 📅 機構記憶時間軸（Append-Only，永不覆蓋）
> ### 2026-01-15 — 專家訪談（第一次）
> （逐字稿摘要 Append 於此）
>
> ### （後續紀錄往下累積）
```

---

## 十二、Demo 劇本（本模組部分）

```
[Step 1] 分析師將 X精密.md 的 status 改為 "vault"（一鍵立案）

[Step 2] 切換到 02_Fact_Vault/entities/
  └── X精密 自動搬移、Pre-DD wiki 自動生成
  └── 商工登記基本資料已自動填入
  └── 丟入當天第一手專家訪談紀錄 → 沉澱進機構記憶時間軸

[Step 3] 回到 _index.md → Pipeline Dashboard 自動更新顯示 X精密 在 pipeline 清單
```

---

## 十三、費用與成本估算（本模組）

| 方案 | 限制 | 費用 |
|------|------|------|
| 免費（AI Studio）| 每天 50 次請求、每分鐘 2 次 | $0 |
| 付費 | 無限制 | ~$0.10–0.50 / 份文件 |

### 開發工時估算（本模組）

| 階段 | 內容 | 估計 |
|------|------|------|
| 立案模組 + 商工登記 | status 偵測 + 自動查詢填入 + Pre-DD 生成 | 2–3 小時 |
| Profile Insights 模組 | 文件萃取 + 去重 + 衝突標記 + 資料夾模式偵測 | 3–4 小時 |
| Pipeline Dashboard | Dataview 查詢設計 + _index.md | 2–3 小時 |
| Obsidian 模板 + Config | entity 模板、折疊區塊 | 1–2 小時 |
| Seed Data 測試 + Debug | 用真實訪談紀錄跑通、修正輸出問題 | 2–3 小時 |
| **合計** | | **約 10–15 小時** |

---

## 十四、設計原則與邊界

| 原則 | 說明 |
|------|------|
| 事實鐵紀律 | Prompt 硬性禁止 AI 推論，無原文不輸出 |
| Append-Only | 重複公司只加新佐證，不覆蓋舊資料 |
| 本機優先 | 所有資料存於本機 Obsidian Vault |
| 手動可介入 | Obsidian 原生編輯，任何欄位均可手動修改 |

### Watchdog 防護機制（status: vault 觸發）

| 防護層 | 機制 | 防止的問題 |
|--------|------|-----------|
| Debounce | 收到 modified event 後等 1.5 秒，靜止後才執行 | Obsidian 連續儲存觸發多次搬移 |
| Processed Set | 維護 `processed_files.json`，已搬移過的路徑直接跳過 | 搬移後再編輯觸發重複搬移 → crash |
| 路徑檢查 | 偵測到路徑含 `02_Fact_Vault` 則不處理 | 已在 Vault 的檔案被誤觸發 |

**processing_lock 欄位**：搬移開始時於 YAML Frontmatter 寫入 `processing_lock: true`，完成後移除。程式中途 crash 重啟時可識別「搬一半」的檔案，避免資料損毀。

---

## 十五、未來擴充（不在 MVP 範圍）

- **Phase 2**：自動定期重跑，批次更新所有追蹤公司的線上資訊，無需手動觸發
- **Phase 3**：多賽道橫向比較 Dashboard
- **Phase 4**：多人共用版（Web UI）

---

*本規格書為標的管理模組（Fact Vault）唯一依據。標的偵測模組見 SPEC_A_標的偵測.md。*
