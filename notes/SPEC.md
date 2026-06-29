# EMS — 投研持久化事實雷達系統
## 最終產品規格書 v1.0
**建立日期**：2026-05-27  
**負責人**：Brandon Chen  
**狀態**：已對齊，待開發

---

## 一、工具定位與核心主軸

**工具全名**：投研持久化事實雷達系統（Evidence Management System, EMS）  
**專案代號**：PE KM Tool

### 核心價值命題
將分析師手動翻閱年報、刷 104 職缺才能發現的「未上市供應鏈隱形冠軍」，交給 AI 自動萃取並沉澱成不會遺忘的機構知識庫。

### 鐵律
- **只碰 100% 事實**：嚴禁任何推論、猜測、關聯性連連看
- **Append-Only**：知識只增不改，保留完整歷史佐證鏈
- **本機優先**：所有資料存於本機，無雲端資料庫

---

## 二、核心功能模組

### 模組 1｜進攻端 — 事實獵手（The Fact Hunter）

**觸發方式**：分析師將文件丟入 `raw_inputs/` 資料夾，Watchdog 自動偵測並處理

**支援輸入格式**：
- PDF 年報（主力：大廠供應商揭露頁）
- 104 職缺文字（複製貼上為 .txt）
- 政府公告文字（補助、得標公告等）

**目標提取範圍**：
- ✅ 未上市公司（無任何股票代號）
- ✅ 興櫃公司（尚未正式掛牌，估值未被充分定價）
- ❌ 排除：上市（TWSE）+ 上櫃（OTC）公司

**AI 任務**：
- 年報：只抓符合上述範圍的公司，精確記錄頁碼 + 原文脈絡
- 104 職缺：只抓包含賽道關鍵字（如台積電、CoWoS、先進封裝）的未上市 / 興櫃企業
- 排除判斷依據：文件中出現四位數台股代號（如 2330、3035）或明確標示「上市」「上櫃」字樣者，一律排除；興櫃代號或無代號者保留

**產出**：
- 自動追加至 `track_trees/{賽道名稱}.md`（賽道樹狀圖）
- 以 `[[公司名稱 (未上市)]]` WikiLink 語法標記，可點擊
- 佐證以 Blockquote 呈現（原文、頁碼、關係描述）
- 同一公司有新佐證時：Append 新來源 + 標記「⚡ 新增佐證來源」

---

### 模組 1 補充｜雙路徑設計

#### Discovery Mode（主要路徑）
分析師將外部文件（大廠年報、產業報告、政府公告）丟入 `raw_inputs/`，AI 從文件中挖掘符合條件的未上市 / 興櫃公司。

#### Research Mode（直接鎖定公司）
分析師直接輸入目標公司名稱，系統主動從四個來源抓取資料並整合成結構化 profile：

| 來源 | 抓取內容 |
|---|---|
| 商工登記 | 負責人、資本額、設立日期 |
| 104 職缺 | 近期招募方向、擴線訊號 |
| 公司官網 | 主力產品、客戶描述 |
| 新聞 | 近期媒體曝光、重大事件（不限定來源）|

所有來源均附確認連結。LinkedIn 排除 MVP 範圍（需登入驗證，複雜度高）。  
整合後生成結構化 profile，可直接 vault 進模組 B。

#### 補充搜尋（半自動觸發）
Discovery Mode 發現公司後，分析師可對感興趣的公司手動點擊「補充搜尋」，觸發與 Research Mode 相同的四來源抓取。不感興趣的公司不觸發，避免無用資料堆積。

---

### 多格式文件支援

| 格式 | 處理方式 | 可靠度 |
|---|---|---|
| PDF | Gemini 原生讀取 | 高 |
| Word (.docx) | 文字抽取後交 Gemini | 高 |
| Excel (.xlsx) | 轉 CSV 後結構化處理 | 中（複雜表格有誤差）|
| 掃描件 / 圖片 PDF | OCR 後再處理 | 中低（依掃描解析度）|
| 純文字 (.txt) | 直接處理 | 高 |

**處理失敗行為**：系統在公司 profile 頁產生警示紀錄，標注「XX 文件未能成功解析，請手動確認」，不靜默失敗。

---

### 資料夾模式偵測

系統以文件所在資料夾判斷萃取模式，無需 AI 判斷或分析師手動選擇：

| 資料夾 | 萃取模式 | 說明 |
|---|---|---|
| `raw_inputs/` | 選擇性萃取 | 外部文件，找出對目標公司的片段提及 |
| `companies/X精密/documents/` | 結構化萃取 | 公司專屬文件，對全文做完整 Insight 萃取 |

各資料夾均放置 `_README.md` 說明應放置的文件類型。

**文件誤放偵測**：文件進入 `documents/` 時，系統自動確認相關性（文件提及公司名稱的比例）。比例偏低時跳出警示建議移至 `raw_inputs/`，不強制阻擋。

---

### 模組 2｜防禦端 — 事實大本營（The Fact Vault）

#### Stage 分類系統

每家公司在 YAML Frontmatter 標記所處投研階段，系統自動彙整各 Stage 的公司清單：

| Stage | 說明 |
|-------|------|
| `pipeline` | 初步觀察，尚未正式研究 |
| `researching` | 深度調研中 |
| `ic_ready` | 資料備齊，準備提交投資委員會 |
| `portfolio` | 已投資，進入投後管理 |
| `exited` | 已退出 |

---

#### Pipeline Dashboard（`_index.md`）

`02_Fact_Vault/_index.md` 為 Module B 首頁，以 Obsidian **Dataview** 外掛自動產生動態 Pipeline 視圖：

- **總覽區**：各 Stage 公司數量一覽
- **清單區**：點擊 Stage 展開，顯示該 Stage 所有公司

**公司清單欄位：**

| 欄位 | 來源 YAML 欄位 |
|---|---|
| 公司名稱（WikiLink，點擊進入 profile）| 檔案名稱 |
| 賽道 | `track` |
| 文件數 | `doc_count` |
| 發現日期 | `created` |
| 最後更新 | `last_doc_update` |

Dataview 動態更新，新增公司或 stage 變更後自動反映，無需手動維護清單。

---

**入口 A：從 Fact Hunter 升級**
1. 分析師點開 `[[X精密 (未上市)]]`，在 YAML Frontmatter 改 `status: "vault"` 並設定初始 `stage: "pipeline"`
2. Watchdog 偵測到狀態變更，自動執行：
   - 將檔案搬移至 `02_Fact_Vault/entities/`
   - 將歷史佐證鏈格式化寫入 Profile
   - 觸發商工登記自動查詢，填入基本資料

**入口 B：手動建立**
1. 分析師直接在 `02_Fact_Vault/entities/` 新增公司 Markdown 檔
2. 在 YAML Frontmatter 設定 `status: "vault"` + `stage` + 基本資訊
3. 上傳已有資料至系統，AI 解析後建成知識基底
4. 與入口 A 共用同一套模板與後續流程

---

#### 文件自動解析 → Profile Insights（核心賣點）

**觸發方式**：分析師將任何公司相關文件（訪談逐字稿、新聞、研究報告、財報、會議紀錄）丟入該公司的 `documents/` 資料夾，Watchdog 自動偵測並處理。

**AI 任務**：
- 讀取文件全文，針對「這家公司」萃取關鍵 insights（而非像 Fact Hunter 那樣找新公司）
- 每條 insight 精確標記來源：檔案名稱 + 頁碼 / 段落
- 自動 Append 至 Profile 的「AI 綜整摘要」區塊

**三個品質機制**：

| 機制 | 說明 |
|------|------|
| **去重** | 相同 insight 出現在多份文件時合併，並列出所有來源 |
| **衝突標記** | 矛盾資訊（如兩份文件給出不同營收數字）標示 `⚠️ 衝突` 並並列兩個來源，不自動選邊 |
| **來源追溯** | 每條 insight 可點回原始文件段落，不憑空產生 |

**Pre-DD 黃頁自動填入（商工登記）**：
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

**機構記憶時間軸**：
- 每次新增訪談紀錄、調研報告、會議紀錄，Append 至時間軸區塊
- 永不覆蓋，完整保留歷史

---

## 三、技術架構

```
分析師丟入文件
      ↓
raw_inputs/ 資料夾
      ↓
librarian.py（Watchdog 自動監控）
      ↓
Gemini 1.5 Pro API（整本 PDF 原生解讀，2M Token 視窗）
      ↓
Pydantic 強制 JSON 格式校驗
      ↓
寫入 Obsidian Vault（純 Markdown，本機存儲）
      ↓
Log 檔記錄（每次處理結果）
```

### 技術棧

| 元件 | 選型 | 理由 |
|------|------|------|
| AI 模型 | Gemini 1.5 Pro | 原生 PDF 解讀、2M Token、免費額度夠用 |
| 資料夾監控 | watchdog（Python）| 自動偵測新檔案，無需手動觸發 |
| 資料校驗 | Pydantic | 強制 JSON 格式，確保 100% 可解析 |
| 知識庫介面 | Obsidian Vault | KM 功能內建、Graph View 可視化、WikiLink |
| 賽道設定 | tracks.yaml | Config 驅動，新增賽道不改程式碼 |
| 公司資料查詢 | 經濟部商工登記 API | 自動填入 Pre-DD 基本欄位 |

---

## 四、Pydantic 資料結構

```python
from pydantic import BaseModel, Field
from typing import List, Literal

class ExtractedEntity(BaseModel):
    entity_name: str = Field(description="未上市或興櫃公司之法定全稱或明確簡稱")
    source_type: Literal["Annual_Report", "Job_Posting", "Gov_Grant"]
    evidence_quote: str = Field(description="100% 複製原文之關鍵事實文本")
    page_number: int = Field(description="年報頁碼；文字檔填 0")
    context_relation: str = Field(description="與大廠的物理事實關係")
    unlisted_evidence: str = Field(description="文件中支持此公司為未上市／興櫃的原文依據；若無明確依據禁止輸出")
    confidence: Literal["high", "medium", "low"] = Field(description="high=文件明確無股票代號；medium=未見代號但未明確排除；low=有模糊跡象，需人工確認")

class TrackTreePayload(BaseModel):
    track_name: str = Field(description="賽道代號，如 semiconductor_advanced_packaging")
    discovered_entities: List[ExtractedEntity]

# ── 文件解析 → Profile Insights 用 ──────────────────────────

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

## 五、目錄結構

```
PE KM tool/
├── .env                          # GEMINI_API_KEY（不進 git）
├── librarian.py                  # 核心調度腳本
├── requirements.txt              # 依賴套件
├── tracks.yaml                   # 賽道設定（關鍵字、樹狀圖檔名）
├── processing.log                # 處理紀錄流水帳
├── prompts/
│   └── extract_facts.txt         # 嚴格事實提取 System Prompt
├── notes/
│   ├── SPEC.md                   # 本規格書
│   └── HANDOFF.md                # Session 交接紀錄
└── Obsidian_Vault/
    ├── 01_Fact_Hunter/
    │   ├── raw_inputs/           # Discovery Mode：外部文件（年報、產業報告）
    │   │   └── _README.md        # 說明：放外部文件，AI 從中找目標公司
    │   └── track_trees/          # AI 自動編譯賽道樹狀圖
    │       └── 先進封裝賽道.md
    └── 02_Fact_Vault/
        └── entities/             # 立案公司 Wiki 頁面
            ├── X精密/
            │   ├── X精密.md      # Profile 主頁（三區設計：AI 區 / 分析師區 / 歷史區）
            │   └── documents/    # 公司專屬文件（AI 做完整結構化萃取）
            │       └── _README.md  # 說明：只放此公司的專屬文件
            └── _index.md         # Pipeline Dashboard（Dataview 動態產生）
```

---

## 六、賽道設定（tracks.yaml 範例）

```yaml
tracks:
  semiconductor_packaging:
    name: 半導體先進封裝
    keywords:
      - 台積電
      - CoWoS
      - 先進封裝
      - 探針卡
      - Fab
      - 電鍍
    tree_file: 先進封裝賽道.md
    
  # 未來新增賽道：加在這裡，不改程式碼
  # biotech:
  #   name: 生技醫療
  #   keywords: [CDMO, 原料藥]
  #   tree_file: 生技賽道.md
```

---

## 七、公司 Profile 頁面模板（entities/X精密/X精密.md）

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

## 八、System Prompt（extract_facts.txt）

```
你是一個極度嚴謹的私募股權投資（PE）數據審計 Agent。
你的任務是從輸入的文本或 PDF 中，提取供應鏈中的「未上市」或「興櫃」隱形冠軍企業。

【目標範圍】
✅ 保留：未上市公司（無任何台股代號）
✅ 保留：興櫃公司（尚未正式於 TWSE / OTC 掛牌）
❌ 排除：台股上市公司（TWSE，如 2330 台積電）
❌ 排除：台股上櫃公司（OTC，如 3035 智原）
❌ 排除：美股、港股、其他交易所之上市企業

【排除判斷信號】
凡文件中出現該公司名稱旁附有四位數台股代號，或明確標示「上市」「上櫃」字樣者，一律排除。
興櫃代號或無任何股票代號者保留。

【嚴格指令】
1. 事實至上：只准提取文本中「黑字白紙寫出來的物理事實」。嚴禁任何推論、猜測或可能的關聯性。
2. 強制舉證：每筆輸出必須填寫 unlisted_evidence，說明你認定此公司為未上市／興櫃的文件依據（原文）。若無明確依據，禁止輸出。
3. 無證據不輸出：若文件中沒有符合條件的公司，請直接返回空的 JSON 列表。
4. 頁碼精確度：輸入為 PDF 時，必須提供實際頁碼（Page Number）。
5. confidence 標記：high = 文件明確無股票代號；medium = 未見代號但未明確排除；low = 有模糊跡象，需人工確認。

請將結果嚴格按照提供的 JSON Schema 輸出。
```

---

## 九、使用者旅程 / Demo 劇本

```
[Step 1] 打開 Obsidian → 進入 01_Fact_Hunter/track_trees/
  └── 展示由 5 本大廠年報 + 職缺自動編譯的「先進封裝賽道樹狀圖」
  └── 發現系統自動點亮外界沒注意到的未上市標的：[[X精密 (未上市)]]
  └── 點開看到 100% 準確的佐證鏈：
        「弘塑 2025 年報第 42 頁載明為前三大供應商」（原文複製）

[Step 2] 分析師將 X精密.md 的 status 改為 "vault"（一鍵立案）

[Step 3] 切換到 02_Fact_Vault/entities/
  └── X精密 自動搬移、Pre-DD wiki 自動生成
  └── 商工登記基本資料已自動填入
  └── 丟入當天第一手專家訪談紀錄 → 沉澱進機構記憶時間軸
```

---

## 十、費用與成本估算

### Gemini API 費用
| 方案 | 限制 | 費用 |
|------|------|------|
| 免費（AI Studio）| 每天 50 次請求、每分鐘 2 次 | $0 |
| 付費 | 無限制 | ~$0.10–0.50 / 份年報 |

> MVP 階段免費額度完全足夠，不需開啟付費。

### 開發工時估算

| 階段 | 內容 | 估計 |
|------|------|------|
| 專案骨架 + 環境設置 | 資料夾、requirements、.env、README.md | 1–2 小時 |
| 事實獵手（Discovery Mode） | Watchdog + Gemini + Prompt 調優 + Pydantic + Obsidian 寫入 | 5–7 小時 |
| Research Mode（直接查詢） | 四來源資料抓取 + 整合 + 補充搜尋觸發 | 5–8 小時 |
| 多格式文件解析 + 錯誤處理 | PDF / Word / Excel / 掃描件 + 失敗通知 | 3–5 小時 |
| 立案模組 + 商工登記 | status 偵測 + 自動查詢填入 + Pre-DD 生成 | 2–3 小時 |
| Profile Insights 模組 | 文件萃取 + 去重 + 衝突標記 + 資料夾模式偵測 | 3–4 小時 |
| Pipeline Dashboard | Dataview 查詢設計 + _index.md | 2–3 小時 |
| Obsidian 模板 + Config | tracks.yaml、entity 模板、折疊區塊 | 1–2 小時 |
| Seed Data 測試 + Debug | 用真實年報跑通、修正輸出問題 | 5–8 小時 |
| **合計（可執行原型）** | | **約 27–42 小時（4–6 天）** |

> **Demo 品質（可信服決策層）**：原型完成後，需再 2–3 週進行 Prompt 調優、真實資料驗證、邊界情況修正，才達可展示水準。  
> **現階段設計為單人使用**；多人共用版列為 Phase 4。

---

## 十一、設計原則與邊界

| 原則 | 說明 |
|------|------|
| 事實鐵紀律 | Prompt 硬性禁止 AI 推論，無原文不輸出 |
| Append-Only | 重複公司只加新佐證，不覆蓋舊資料 |
| 本機優先 | 所有資料存於本機 Obsidian Vault |
| 架構可擴充 | 未來加 sourcing agent 只需插入 raw_inputs/ 前端 |
| 賽道可切換 | 改 tracks.yaml 即可，不動程式碼 |
| 手動可介入 | Obsidian 原生編輯，任何欄位均可手動修改 |

### Watchdog 防護機制（status: vault 觸發）

Watchdog 監控的是檔案系統事件（file modified），需三層防護避免 crash：

| 防護層 | 機制 | 防止的問題 |
|--------|------|-----------|
| Debounce | 收到 modified event 後等 1.5 秒，靜止後才執行 | Obsidian 連續儲存觸發多次搬移 |
| Processed Set | 維護 `processed_files.json`，已搬移過的路徑直接跳過 | 搬移後再編輯觸發重複搬移 → crash |
| 路徑檢查 | 偵測到路徑含 `02_Fact_Vault` 則不處理 | 已在 Vault 的檔案被誤觸發 |

**processing_lock 欄位**：搬移開始時於 YAML Frontmatter 寫入 `processing_lock: true`，完成後移除。程式中途 crash 重啟時可識別「搬一半」的檔案，避免資料損毀。

---

## 十二、未來擴充路線圖（不在 MVP 範圍）

- **Phase 2**：自動定期重跑 — 系統排程對所有追蹤中公司的線上資訊做批次更新，無需手動觸發
- **Phase 3**：多賽道橫向比較 Dashboard
- **Phase 4**：多人共用版（Web UI）

---

*本規格書為 EMS MVP 唯一依據，所有開發決策以此為準。*
