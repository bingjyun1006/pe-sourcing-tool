# PE Sourcing Tool

> 私募股權供應鏈情報工具 — 以 AI 自動從大廠財報萃取未上市供應鏈標的，建立可持續追蹤的賽道知識庫。

**Live Demo**：[pe-sourcing-tool.onrender.com](https://pe-sourcing-tool.onrender.com)

---

## 目錄

- [背景與動機](#背景與動機)
- [核心功能](#核心功能)
- [系統架構](#系統架構)
- [快速開始](#快速開始)
- [部署指南（Render）](#部署指南render)
- [使用說明](#使用說明)
- [資料儲存與同步](#資料儲存與同步)
- [檔案結構](#檔案結構)
- [已知限制](#已知限制)
- [技術棧](#技術棧)

---

## 背景與動機

PE 盡職調查的核心挑戰之一，是在公開資訊極為有限的情況下，系統性地找出值得投資的**未上市供應鏈隱形冠軍**。

傳統做法是人工翻閱財報附表，逐筆整理被投資公司或供應商名稱，耗時且難以跨案例積累知識。

本工具以 AI 自動化這個過程：

- **輸入**：大廠年報 PDF 或合併財報 PDF
- **輸出**：結構化的潛在未上市標的清單，含業務描述、上市狀態、供應鏈層級定位

---

## 核心功能

| 功能 | 說明 |
|------|------|
| **T1 年報軌道** | 上傳大廠年度報告，從採購揭露條款萃取供應商（含未上市） |
| **T2 財報軌道** | 上傳合併財務報告，從附表九／附表六萃取被投資未上市公司 |
| **供應鏈骨架地圖** | AI 動態生成 L1–L4 供應鏈層級結構，標示已知大廠位置 |
| **T1/T2 建議清單** | AI 推薦值得上傳分析的大廠名單，附推薦理由 |
| **公司簡介查詢** | 點擊任一潛在標的，即時查詢業務概述、成立年份、主要客戶群 |
| **書籤與追蹤清單** | 對感興趣公司加星號，一鍵匯出追蹤清單 CSV |
| **多賽道管理** | 可同時建立並切換多個賽道（如：散熱模組、先進封裝、被動元件） |
| **手動新增／刪除** | 可手動補充 AI 未萃取到的公司，支援刪除 |
| **自動同步** | 每次查詢後自動將結果回寫 GitHub，多人使用紀錄不遺失 |

---

## 系統架構

```
使用者輸入關鍵字
      │
      ▼
Gemini 生成供應鏈骨架地圖（L1–L4）
      │
      ▼
Gemini 推薦值得上傳的大廠清單
      │
      ▼
使用者上傳年報 / 合併財報 PDF
      │
      ▼
PyMuPDF 讀取全文（1M tokens 以內一次處理）
      │
      ▼
Gemini 2.5 Flash 萃取
  ├─ T1：供應商名稱 + 業務描述
  └─ T2：被投資公司 + 持股比例 + 業務描述
      │
      ▼
後處理過濾
  ├─ TWSE 資料庫比對上市狀態
  ├─ 過濾境外公司（香港、澳門、中國、韓國等）
  ├─ 過濾純控股 / 投資公司
  └─ 過濾金融 / 不動產等無關業務
      │
      ▼
寫入賽道 Markdown 檔 + details JSON
      │
      ▼
Streamlit UI 顯示潛在目標清單
      │
      ▼
背景 git push 回 GitHub（自動同步）
```

### 技術選型原因

| 選擇 | 原因 |
|------|------|
| Gemini 2.5 Flash | 1M context window，完整財報一次處理；免費額度足夠 MVP |
| Streamlit | Python 原生 UI，無需前端開發，快速 MVP |
| PyMuPDF | 中文 PDF 讀取穩定，比 pdfplumber 編碼問題少 |
| Markdown 儲存 | 純文字，易讀、易轉移、可進 git、不依賴資料庫 |
| GitHub 自動同步 | 讓雲端部署的查詢紀錄持久保存，多人共用不遺失 |

---

## 快速開始

### 前置條件

1. Python 3.10+
2. Gemini API Key：前往 [aistudio.google.com/apikey](https://aistudio.google.com/apikey) 免費申請

### 本地端啟動

```bash
# 複製專案
git clone https://github.com/bingjyun1006/pe-sourcing-tool.git
cd pe-sourcing-tool

# 安裝相依套件
pip install -r requirements.txt

# 啟動
python -m streamlit run app.py --server.port 8502
```

瀏覽器開啟 `http://localhost:8502`，在頂端輸入 Gemini API Key 即可使用。

### 環境變數（選填）

| 變數名稱 | 說明 |
|----------|------|
| `GEMINI_API_KEY` | 預先設定 API Key，省去每次手動輸入 |
| `GITHUB_TOKEN` | GitHub Personal Access Token，啟用自動同步功能 |
| `GITHUB_REPO` | 同步目標 repo，格式：`owner/repo-name` |

---

## 部署指南（Render）

1. Fork 本 repo 至你的 GitHub 帳號或 Organization
2. 前往 [render.com](https://render.com) 建立新的 **Web Service**
3. 連接 GitHub repo，設定如下：
   - **Runtime**：Python
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
4. Environment Variables 設定：

   | Key | Value |
   |-----|-------|
   | `GEMINI_API_KEY` | （選填）預設 API Key |
   | `GITHUB_TOKEN` | GitHub PAT，需有 repo Contents 讀寫權限 |
   | `GITHUB_REPO` | `your-org/pe-sourcing-tool` |

5. Deploy → 等待部署完成，複製 Render URL 分享給團隊

> **注意**：Render free tier 閒置 15 分鐘後會 sleep，首次訪問需等待約 30–60 秒 cold start。

---

## 使用說明

### 操作流程

1. 輸入 Gemini API Key（部署版每次進入需重新輸入，或由管理者預設）
2. 在搜尋欄輸入賽道關鍵字（例：散熱模組、先進封裝、被動元件）
3. 點擊「◈ 分析賽道」→ 生成供應鏈骨架地圖與 T1/T2 建議清單
4. 依建議清單上傳對應大廠的年報（T1）或合併財報（T2）PDF
5. 點擊「▶ 開始分析」→ 等待 AI 萃取（30 秒至數分鐘，依 PDF 大小而定）
6. 在「已發現潛在目標」查看結果，點擊公司名稱查詢詳細簡介
7. 對感興趣公司按 ★ 加入追蹤，匯出 CSV 進行後續研究

### 上傳文件選擇原則

| 文件類型 | 上傳至 | 預期產出 | 備註 |
|----------|--------|----------|------|
| 年度報告（Annual Report） | T1 | 供應商名稱 | 多數大廠以代號取代，0 筆屬正常現象 |
| 合併財務報告（含附表九） | T2 | 被投資公司清單 | 資訊較完整，萃取成功率高 |

> **建議優先使用 T2**。T1 受限於大廠揭露程度，萃取結果不穩定。

---

## 資料儲存與同步

### 儲存位置

| 資料類型 | 路徑 |
|----------|------|
| 賽道潛在目標清單 | `Obsidian_Vault/01_Fact_Hunter/track_trees/` |
| 供應鏈骨架地圖 + 推薦快取 | `data/searches/` |
| 公司簡介快取 | `data/company_briefs/` |
| 已儲存賽道清單 | `data/saved_tracks.json` |
| 賽道設定 | `tracks.yaml` |

### 自動同步機制

設定 `GITHUB_TOKEN` 環境變數後，以下操作會自動在背景將結果 push 回 GitHub：

- 執行「◈ 分析賽道」後
- PDF 萃取完成後
- 查詢公司簡介後（首次查詢）
- 儲存賽道後
- 手動新增公司後

這確保多人在雲端部署版上的操作紀錄不會因 instance 重啟而遺失。

> **注意**：AI 萃取資料僅供研究參考，上市狀態與業務描述建議再次核實查驗。

---

## 檔案結構

```
pe-sourcing-tool/
├── app.py                          # Streamlit UI 主程式
├── librarian.py                    # 核心業務邏輯（AI 萃取、過濾、儲存）
├── tracks.yaml                     # 賽道關鍵字設定
├── requirements.txt
│
├── data/
│   ├── searches/                   # 供應鏈地圖 + 推薦快取（JSON）
│   ├── company_briefs/             # 公司簡介快取（JSON）
│   ├── saved_tracks.json           # 已儲存賽道清單
│   ├── listed_companies.json       # TWSE 上市公司資料庫
│   └── bookmarks_*.json            # 各賽道書籤
│
└── Obsidian_Vault/
    └── 01_Fact_Hunter/
        └── track_trees/            # 各賽道潛在目標清單（Markdown）
```

---

## 已知限制

| 限制 | 說明 |
|------|------|
| T1 萃取率低 | 多數上市公司年報以代號取代供應商名稱，屬正常現象 |
| Render cold start | Free tier 閒置後首次訪問需等待 30–60 秒 |
| Gemini 配額 | 免費額度有限，大量使用建議升級 API 方案 |
| AI 準確性 | 上市狀態與業務描述為 AI 判斷，仍需人工核實 |
| 無用戶系統 | API Key 存於 browser session，不跨裝置保存 |

---

## 技術棧

| 項目 | 技術 |
|------|------|
| AI 模型 | Google Gemini 2.5 Flash |
| UI 框架 | Streamlit |
| PDF 讀取 | PyMuPDF |
| 資料格式 | Markdown + JSON |
| 部署 | Render |
| 版本控制 / 資料同步 | GitHub |
