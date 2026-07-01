"""
Sector Radar — Streamlit UI
執行：python -m streamlit run app.py --server.port 8502
"""

import csv
import html as html_lib
import io
import json
import os
import re as _re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import streamlit as st

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from librarian import (
    RAW_INPUTS_DIR,
    TRACK_TREES_DIR,
    VAULT_DIR,
    get_track_pdf_dir,
    generate_recommendations,
    generate_research_brief,
    generate_skeleton_map,
    suggest_scene_contexts,
    load_tracks,
    process_file,
    purge_source_from_tree,
    save_search_result,
    load_search_history,
    load_company_details,
    generate_company_brief,
    load_company_brief,
    save_company_brief,
    load_processed_files,
    save_processed_files,
    load_file_source_types,
    save_file_source_type,
    is_foreign_company,
    load_saved_tracks,
    save_track,
    delete_track,
    rename_track_label,
    manual_add_to_tree,
    delete_manual_entry,
    set_gemini_api_key,
    get_listing_status,
    SkeletonMap,
    BriefRecommendations,
)

st.set_page_config(
    page_title="PE Sourcing Tool",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=DM+Sans:wght@300;400;500&display=swap');

/* ── 全域縮放（等同瀏覽器 85% zoom）── */
body { zoom: 0.85; }

/* ── 基底 ── */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
    background-color: #F7F4EE !important;
    font-family: 'DM Sans', sans-serif;
    color: #1A1611;
}
[data-testid="stDecoration"] { display: none !important; }
#MainMenu, footer, header { visibility: hidden; }

.block-container {
    padding: 2.4rem 3rem 3rem !important;
    max-width: 1440px !important;
}

/* ── Header ── */
.sr-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    border-bottom: 1px solid #C8A96E;
    padding-bottom: 1.2rem;
    margin-bottom: 1.8rem;
}
.sr-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 2.4rem;
    font-weight: 500;
    color: #1A1611;
    letter-spacing: 0.03em;
    line-height: 1;
    margin: 0;
}
.sr-eyebrow {
    font-size: 0.65rem;
    font-weight: 400;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #C8A96E;
    margin-bottom: 0.35rem;
}

/* ── 搜尋列 ── */
.search-row {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    margin-bottom: 1.8rem;
}

/* ── Input / Selectbox 統一樣式 ── */
[data-testid="stTextInput"] input,
[data-baseweb="input"] input {
    background-color: #FDFBF7 !important;
    border: 1px solid #D8D0C4 !important;
    border-radius: 3px !important;
    color: #1A1611 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.85rem !important;
    padding: 0.5rem 0.8rem !important;
    box-shadow: none !important;
}
[data-testid="stTextInput"] input:focus,
[data-baseweb="input"] input:focus {
    border-color: #C8A96E !important;
    box-shadow: 0 0 0 2px rgba(200,169,110,0.15) !important;
}
[data-testid="stTextInput"] label {
    font-size: 0.65rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: #6B6254 !important;
}

/* Selectbox */
[data-testid="stSelectbox"] label {
    font-size: 0.65rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: #6B6254 !important;
}
[data-baseweb="select"] > div:first-child {
    background-color: #FDFBF7 !important;
    border: 1px solid #D8D0C4 !important;
    border-radius: 3px !important;
    color: #1A1611 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.84rem !important;
    box-shadow: none !important;
}
[data-baseweb="select"] > div:first-child:hover {
    border-color: #C8A96E !important;
}
[data-baseweb="select"] > div:first-child:focus-within {
    border-color: #C8A96E !important;
    box-shadow: 0 0 0 2px rgba(200,169,110,0.15) !important;
}
/* Dropdown list */
[data-baseweb="popover"] {
    background-color: #FDFBF7 !important;
    border: 1px solid #D8D0C4 !important;
    border-radius: 3px !important;
    box-shadow: 0 4px 16px rgba(26,22,17,0.08) !important;
}
[role="option"] {
    background-color: #FDFBF7 !important;
    color: #1A1611 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.84rem !important;
}
[role="option"]:hover,
[role="option"][aria-selected="true"] {
    background-color: #F0EAD6 !important;
    color: #1A1611 !important;
}
/* Arrow icon color */
[data-baseweb="select"] svg { fill: #8A7F6E !important; }

/* ── 按鈕 基礎 ── */
[data-testid="stButton"] button {
    border-radius: 3px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    padding: 0.5rem 1.1rem !important;
    transition: background 0.18s, color 0.18s, border-color 0.18s !important;
    white-space: nowrap !important;
}
/* Secondary（預設）— 輕量暖色調；同時覆蓋舊版(baseButton)與新版(stBaseButton) */
[data-testid="baseButton-secondary"],
[data-testid="stBaseButton-secondary"] {
    background: #F0EDE6 !important;
    color: #4A4035 !important;
    border: 1px solid #C8B99A !important;
}
[data-testid="baseButton-secondary"]:hover,
[data-testid="stBaseButton-secondary"]:hover {
    background: #EDE9DF !important;
    border-color: #C8A96E !important;
    color: #1A1611 !important;
}
/* Primary — 深色主動作 */
[data-testid="baseButton-primary"],
[data-testid="stBaseButton-primary"] {
    background: #1A1611 !important;
    color: #FAF8F3 !important;
    border: none !important;
}
[data-testid="baseButton-primary"]:hover,
[data-testid="stBaseButton-primary"]:hover {
    background: #C8A96E !important;
    color: #1A1611 !important;
}
/* Disabled */
[data-testid="stButton"] button:disabled {
    background: #E8E4DC !important;
    color: #B0A890 !important;
    border-color: #D8D0C4 !important;
    cursor: not-allowed !important;
}

/* ── 軌道卡片 ── */
.track-card {
    background: #FDFBF7;
    border: 1px solid #E2DDD4;
    border-radius: 4px;
    padding: 1.4rem 1.3rem 1.6rem;
}
.track-label {
    font-size: 0.6rem;
    font-weight: 500;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #C8A96E;
    margin-bottom: 0.2rem;
}
.track-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.3rem;
    font-weight: 500;
    color: #1A1611;
    margin-bottom: 0.2rem;
}
.track-desc {
    font-size: 0.8rem;
    color: #8A7F6E;
    line-height: 1.55;
    margin-bottom: 1rem;
    padding-bottom: 0.9rem;
    border-bottom: 1px solid #E2DDD4;
}
.section-label {
    font-size: 0.6rem;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #6B6254;
    margin: 1rem 0 0.45rem;
}

/* 推薦項目 */
.rec-item {
    display: flex;
    align-items: flex-start;
    gap: 0.55rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid #EDE9DF;
}
.rec-item:last-child { border-bottom: none; }
.rec-ticker {
    font-size: 0.65rem;
    font-weight: 500;
    color: #FAF8F3;
    background: #2C2416;
    padding: 2px 5px;
    border-radius: 2px;
    white-space: nowrap;
    flex-shrink: 0;
    margin-top: 2px;
}
.rec-name  { font-size: 0.92rem; font-weight: 500; color: #1A1611; }
.rec-reason { font-size: 0.8rem; color: #8A7F6E; line-height: 1.4; margin-top: 1px; }

/* 軌道三 */
.t3-item {
    padding: 0.45rem 0;
    border-bottom: 1px solid #EDE9DF;
}
.t3-item:last-child { border-bottom: none; }
.t3-company { font-size: 0.82rem; font-weight: 500; color: #1A1611; }
.t3-meta    { font-size: 0.68rem; color: #8A7F6E; margin-top: 2px; }
.tag {
    display: inline-block;
    font-size: 0.56rem;
    font-weight: 500;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    padding: 1px 5px;
    border-radius: 2px;
    margin-right: 4px;
    vertical-align: middle;
}
.tag-sbir { background: #E8EAF4; color: #3A4A8A; }

/* Sweet Spot */
.sweet-block {
    background: linear-gradient(135deg, #2C2416, #3D3120);
    border-radius: 3px;
    padding: 0.75rem 1rem;
    margin-top: 0.8rem;
}
.sweet-title {
    font-size: 0.6rem;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #C8A96E;
    margin-bottom: 0.35rem;
}
.sweet-co { font-size: 0.82rem; color: #FAF8F3; padding: 2px 0; }

/* ── File uploader ── */
[data-testid="stFileUploaderDropzone"] {
    background: #F5F1EB !important;
    border: 1px dashed #C4B99A !important;
    border-radius: 3px !important;
}
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzone"] p,
[data-testid="stFileUploaderDropzone"] small {
    font-size: 0.71rem !important;
    color: #8A7F6E !important;
}
/* Browse files 按鈕覆寫（不要用全域黑色按鈕樣式） */
[data-testid="stFileUploaderDropzone"] button {
    background: #FDFBF7 !important;
    color: #4A4035 !important;
    border: 1px solid #C8B99A !important;
    border-radius: 3px !important;
    font-size: 0.7rem !important;
    font-weight: 400 !important;
    letter-spacing: 0.04em !important;
    text-transform: none !important;
    padding: 0.35rem 0.9rem !important;
}
[data-testid="stFileUploaderDropzone"] button:hover {
    background: #EDE9DF !important;
    color: #1A1611 !important;
    border-color: #C8A96E !important;
}

/* ── 搜尋歷史 dropdown ── */
.search-hist-wrap {
    background: #FFFFFF;
    border: 1px solid #D4CEC4;
    border-top: none;
    border-radius: 0 0 8px 8px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.08);
    padding: 4px 0 6px;
    margin-top: -6px;
}
.search-hist-label {
    font-size: 0.58rem;
    color: #A09880;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 4px 14px 2px;
}
.search-hist-wrap div[data-testid="stButton"] button {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    border-bottom: 1px solid #F0EDE8 !important;
    text-align: left !important;
    color: #3A3020 !important;
    font-size: 0.86rem !important;
    padding: 7px 14px !important;
    justify-content: flex-start !important;
}
.search-hist-wrap div[data-testid="stButton"] button:hover {
    background: #F8F5F0 !important;
}
.search-hist-wrap div[data-testid="stButton"] button:last-child {
    border-bottom: none !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    border: 1px solid #E2DDD4 !important;
    border-radius: 4px !important;
    background: #FDFBF7 !important;
}
[data-testid="stExpander"] summary {
    background: #F5F1EB !important;
    color: #4A4035 !important;
    border-radius: 4px !important;
}
[data-testid="stExpander"] summary:hover {
    background: #EDE9DF !important;
    color: #1A1611 !important;
}
[data-testid="stExpander"] summary svg { fill: #8A7F6E !important; }

/* ── Toggle ── */
[data-testid="stToggle"] label,
[data-testid="stToggle"] p,
[data-testid="stToggle"] span,
[data-testid="stToggle"] div,
[data-baseweb="checkbox"] label,
[data-baseweb="checkbox"] span,
[role="switch"] + span,
[role="switch"] ~ div,
.stToggle label, .stCheckbox label {
    color: #4A4035 !important;
    font-size: 0.78rem !important;
}

/* ── 追蹤星號按鈕（最小化）── */
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"])
    > div:first-child [data-testid="stButton"] button {
    background: transparent !important;
    border: none !important;
    padding: 4px 2px !important;
    font-size: 0.9rem !important;
    color: #C8A96E !important;
    min-height: unset !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
    box-shadow: none !important;
}

/* ── 💡 場景建議按鈕（text_input 右側單一按鈕）── */
[data-testid="stHorizontalBlock"]:has(> div:nth-child(1) [data-testid="stTextInput"]):not(:has(> div:nth-child(3)))
    > div:last-child [data-testid="stButton"] button {
    background: #F5F1EB !important;
    color: #8A7F6E !important;
    border: 1px solid #C8B99A !important;
    border-radius: 3px !important;
    padding: 4px 10px !important;
    font-size: 0.9rem !important;
    min-height: unset !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
    box-shadow: none !important;
    transition: all 0.15s !important;
}
[data-testid="stHorizontalBlock"]:has(> div:nth-child(1) [data-testid="stTextInput"]):not(:has(> div:nth-child(3)))
    > div:last-child [data-testid="stButton"] button:hover {
    border-color: #C8A96E !important;
    color: #C8A96E !important;
    background: #EDE9DF !important;
}

/* ── 公司簡介按鈕（簡介，第三欄）── */
/* 條件：第二欄沒有 button（公司列第二欄是文字），排除 chip 列（每欄都是 button） */
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]):not(:has(> div:nth-child(2) [data-testid="stButton"]))
    > div:last-child [data-testid="stButton"] button {
    background: transparent !important;
    border: 1px solid #C8B99A !important;
    border-radius: 3px !important;
    padding: 3px 8px !important;
    font-size: 0.68rem !important;
    color: #8A7F6E !important;
    min-height: unset !important;
    letter-spacing: 0.04em !important;
    text-transform: none !important;
    box-shadow: none !important;
    white-space: nowrap !important;
    transition: all 0.15s !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]):not(:has(> div:nth-child(2) [data-testid="stButton"]))
    > div:last-child [data-testid="stButton"] button:hover {
    border-color: #C8A96E !important;
    color: #C8A96E !important;
    background: rgba(200,169,110,0.06) !important;
}

/* ── 發現公司 ── */
.discovery-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.5rem;
    font-weight: 500;
    color: #1A1611;
}
.discovery-meta { font-size: 0.68rem; color: #8A7F6E; margin-top: 0.15rem; }
.co-card {
    background: #FDFBF7;
    border: 1px solid #E2DDD4;
    border-left: 3px solid #C8A96E;
    border-radius: 3px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.5rem;
}
.co-name { font-family: 'Cormorant Garamond', serif; font-size: 1.05rem; font-weight: 600; color: #1A1611; }
.co-meta { font-size: 0.7rem; color: #8A7F6E; margin-top: 3px; line-height: 1.5; }

/* ── 骨架地圖 ── */
.map-wrap {
    margin: 0.4rem 0 1.8rem;
}
.map-section-label {
    font-size: 0.6rem;
    font-weight: 500;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #6B6254;
    margin-bottom: 0.8rem;
}
.map-flow {
    display: flex;
    align-items: stretch;
    gap: 0;
    overflow-x: auto;
    padding-bottom: 0.4rem;
}
.map-layer-cell {
    display: flex;
    align-items: center;
    gap: 0;
}
.map-layer {
    background: #FDFBF7;
    border: 1px solid #E2DDD4;
    border-radius: 4px;
    padding: 0.9rem 1rem;
    min-width: 155px;
    max-width: 210px;
    flex-shrink: 0;
}
.map-layer.scope-out {
    background: #F5F1EB;
    border-style: dashed;
    border-color: #D8D0C4;
    opacity: 0.55;
}
.map-level {
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #C8A96E;
    margin-bottom: 0.2rem;
}
.map-layer-name {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.2rem;
    font-weight: 600;
    color: #1A1611;
    margin-bottom: 0.25rem;
    line-height: 1.2;
}
.map-layer-desc {
    font-size: 0.84rem;
    color: #8A7F6E;
    line-height: 1.5;
    margin-bottom: 0.6rem;
}
.map-co-chip {
    display: inline-block;
    font-size: 0.8rem;
    background: #EDE9DF;
    color: #4A4035;
    border-radius: 2px;
    padding: 2px 7px;
    margin: 2px 3px 2px 0;
    white-space: nowrap;
}
.map-arrow {
    color: #C8A96E;
    font-size: 1rem;
    padding: 0 0.45rem;
    flex-shrink: 0;
    align-self: center;
    margin-top: -0.2rem;
}

/* ── Misc ── */
hr { border-color: #E2DDD4 !important; margin: 1.6rem 0 !important; }
[data-testid="stAlert"]  { border-radius: 3px !important; font-size: 0.78rem !important; }
[data-testid="stSpinner"] p { font-size: 0.78rem !important; color: #6B6254 !important; }
[data-testid="stExpander"] {
    border: 1px solid #E2DDD4 !important;
    border-radius: 3px !important;
    background: #FDFBF7 !important;
}

/* ── Dialog：點擊 backdrop 不關閉（防止捲軸誤觸關閉） ── */
[data-testid="stModal"] > div:first-child {
    pointer-events: none !important;
}
[data-testid="stModal"] > div:first-child > div {
    pointer-events: auto !important;
}
</style>
""", unsafe_allow_html=True)

# ── Session State ──────────────────────────────────────────────────
# ── API Key 初始化（env var 優先；無則等使用者輸入）────────────────
_env_key = os.environ.get("GEMINI_API_KEY", "").strip()
if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = _env_key
if st.session_state["gemini_api_key"]:
    set_gemini_api_key(st.session_state["gemini_api_key"])

if "brief_cache"       not in st.session_state: st.session_state.brief_cache       = {}
if "skeleton_cache"    not in st.session_state: st.session_state.skeleton_cache    = {}
if "processing_log"    not in st.session_state: st.session_state.processing_log    = []
if "active_keyword"    not in st.session_state: st.session_state.active_keyword    = ""
if "kw_input_widget"       not in st.session_state: st.session_state["kw_input_widget"]       = ""
if "combo_sel_widget"      not in st.session_state: st.session_state["combo_sel_widget"]      = 0
if "_pending_kw"           not in st.session_state: st.session_state["_pending_kw"]           = None
if "_combo_reset_pending"  not in st.session_state: st.session_state["_combo_reset_pending"]  = False
if "scene_context"         not in st.session_state: st.session_state["scene_context"]         = ""
if "_scene_chips"          not in st.session_state: st.session_state["_scene_chips"]          = []
if "_chips_for_kw"         not in st.session_state: st.session_state["_chips_for_kw"]         = ""
if "_pending_scene_ctx"    not in st.session_state: st.session_state["_pending_scene_ctx"]    = None
if "_scene_ctx_keyword"    not in st.session_state: st.session_state["_scene_ctx_keyword"]    = ""
if "_kw_via_dropdown"      not in st.session_state: st.session_state["_kw_via_dropdown"]      = False
if "active_track_name" not in st.session_state: st.session_state.active_track_name = ""
if "history_loaded"    not in st.session_state: st.session_state.history_loaded    = False
if "processed_files"     not in st.session_state: st.session_state.processed_files     = load_processed_files()
if "uploaded_companies"  not in st.session_state: st.session_state.uploaded_companies  = set()
if "_co_brief_cache"     not in st.session_state: st.session_state["_co_brief_cache"]  = {}
if "_clear_confirm"      not in st.session_state: st.session_state["_clear_confirm"]   = False

# ── 公司簡介 Dialog ───────────────────────────────────────────────
@st.dialog("公司簡介", width="large")
def _show_company_card():
    info    = st.session_state.get("_card_info", {})
    name    = info.get("name", "")
    details = info.get("details", {})
    src_co  = info.get("source_company", "")
    track   = info.get("track", "")

    if not name:
        st.error("無公司資料")
        return

    # ── 載入 / 快取簡介（session → 磁碟 → Gemini，依序查）─────────
    cache_key = f"gc::{name}"
    brief = st.session_state["_co_brief_cache"].get(cache_key)
    if brief is None:
        # 先查磁碟快取（sources 非空才採用，否則強制重查）
        disk_brief = load_company_brief(name)
        if disk_brief and disk_brief.get("sources"):
            brief = disk_brief
            st.session_state["_co_brief_cache"][cache_key] = brief
        else:
            with st.spinner(f"正在搜尋 {name} 的公司資訊…"):
                brief = generate_company_brief(
                    company_name=name,
                    evidence_quote=details.get("evidence_quote", ""),
                    source_type=details.get("source_type", ""),
                )
                # 成功且有來源才存磁碟；失敗或 sources 為空不存，讓下次點擊重試
                _ok = "查詢失敗" not in brief.get("business_overview", "")
                _has_src = bool(brief.get("sources"))
                if _ok and _has_src:
                    save_company_brief(name, brief)
                # session cache 只要成功就存（避免同一 session 重複 API 呼叫）
                if _ok:
                    st.session_state["_co_brief_cache"][cache_key] = brief

    # ── Badge helpers ────────────────────────────
    listing = get_listing_status(name)
    _SC = {"上市": ("#E8F0E8","#2A5A2A"), "上櫃": ("#E8EAF4","#2A3A7A"),
           "興櫃": ("#FDF3E0","#7A4A10"), "未上市": ("#F0F0F0","#4A4A4A")}
    _bg, _fg = _SC.get(listing, ("#F0F0F0","#4A4A4A"))
    listing_badge_html = (
        f'<span style="font-size:0.78rem;background:{_bg};color:{_fg};'
        f'border-radius:2px;padding:2px 10px;font-weight:500;vertical-align:middle">'
        f'{html_lib.escape(listing)}</span>'
    )
    # ── Header ──────────────────────────────────
    st.markdown(
        f'<div style="margin-bottom:1.2rem">'
        f'<div style="font-family:\'Cormorant Garamond\',serif;font-size:1.75rem;font-weight:600;'
        f'color:#1A1611;line-height:1.2;margin-bottom:0.5rem">{html_lib.escape(name)}</div>'
        f'<div style="display:flex;gap:0.4rem;align-items:center;flex-wrap:wrap">'
        f'{listing_badge_html}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── 業務概述 ─────────────────────────────────
    overview = brief.get("business_overview", "查無資料")
    st.markdown(
        f'<div style="background:#F5F1EB;border-radius:4px;padding:0.9rem 1rem;margin-bottom:1rem">'
        f'<div style="font-size:0.72rem;font-weight:500;color:#8A7F6E;letter-spacing:0.1em;'
        f'text-transform:uppercase;margin-bottom:0.4rem">業務概述</div>'
        f'<div style="font-size:0.96rem;color:#1A1611;line-height:1.65">{html_lib.escape(overview)}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── 成立年份 & 公司規模 ──────────────────────
    col_yr, col_sz = st.columns(2)
    _card_cell = (
        'border:1px solid #E2DDD4;border-radius:4px;padding:0.7rem 0.9rem;margin-bottom:0.8rem'
    )
    _label_s = (
        'font-size:0.72rem;color:#8A7F6E;letter-spacing:0.08em;'
        'text-transform:uppercase;margin-bottom:0.25rem'
    )
    with col_yr:
        st.markdown(
            f'<div style="{_card_cell}">'
            f'<div style="{_label_s}">成立年份</div>'
            f'<div style="font-size:0.95rem;color:#1A1611">'
            f'{html_lib.escape(brief.get("founded_year","查無資料"))}</div></div>',
            unsafe_allow_html=True
        )
    with col_sz:
        st.markdown(
            f'<div style="{_card_cell}">'
            f'<div style="{_label_s}">公司規模</div>'
            f'<div style="font-size:0.95rem;color:#1A1611">'
            f'{html_lib.escape(brief.get("company_size","查無資料"))}</div></div>',
            unsafe_allow_html=True
        )

    # ── 主要產品 / 服務 ──────────────────────────
    _section_hd = (
        'font-size:0.72rem;font-weight:500;color:#6B6254;letter-spacing:0.08em;'
        'text-transform:uppercase;margin-bottom:0.4rem;border-bottom:1px solid #E2DDD4;padding-bottom:0.3rem'
    )
    _li_style = 'margin-bottom:0.25rem;font-size:0.93rem;color:#4A4035'
    products = brief.get("main_products", ["查無資料"])
    p_items  = "".join(f'<li style="{_li_style}">{html_lib.escape(p)}</li>' for p in products)
    st.markdown(
        f'<div style="margin-bottom:0.85rem">'
        f'<div style="{_section_hd}">主要產品 / 服務</div>'
        f'<ul style="margin:0;padding-left:1.2rem;line-height:1.75">{p_items}</ul>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── 主要客戶群 ───────────────────────────────
    clients = brief.get("main_clients", ["查無資料"])
    c_items = "".join(f'<li style="{_li_style}">{html_lib.escape(c)}</li>' for c in clients)
    st.markdown(
        f'<div style="margin-bottom:0.85rem">'
        f'<div style="{_section_hd}">主要客戶群</div>'
        f'<ul style="margin:0;padding-left:1.2rem;line-height:1.75">{c_items}</ul>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── 在此賽道中的角色（文件原文）───────────────
    ev_quote    = details.get("evidence_quote", "")
    ev_src_type = details.get("source_type", "")

    def _clean_quote(q: str) -> str:
        """壓縮財報原文中的連續空白、去除尾部數字串，並截斷過長文字"""
        import re as _re2
        q = _re2.sub(r'[\s　]+', ' ', q).strip()
        # 財報表格常見：文字後面接一串數字/小數點/貨幣符號（如持股比例、金額欄位）
        q = _re2.sub(r'(\s+[$￥]?[\d,\.]+){2,}\s*$', '', q).strip()
        if len(q) > 160:
            q = q[:157] + "…"
        return q

    rel_cat      = details.get("relation_category", "")
    src_section  = details.get("source_section", "")

    if ev_src_type == "Annual_Report":
        quote_text = "年報僅揭露供應商名稱，未附業務說明"
        is_italic  = True
    elif ev_quote and ev_quote not in ("文件直接點名", ""):
        quote_text = _clean_quote(ev_quote)
        is_italic  = True
    else:
        quote_text = "文件直接點名"
        is_italic  = False

    # 來源標注：公司·軌道 + 附表/段落 + 關係類型
    src_label = f"{src_co}　·　{track}" if src_co else track
    src_meta_parts = []
    if src_section:
        src_meta_parts.append(src_section)
    if rel_cat:
        src_meta_parts.append(rel_cat)
    src_meta = "　·　" + "　·　".join(src_meta_parts) if src_meta_parts else ""

    st.markdown(
        f'<div style="margin-bottom:1rem;border-left:3px solid #C8A96E;'
        f'padding:0.7rem 1rem;background:#FDFBF7;border-radius:0 4px 4px 0">'
        f'<div style="{_label_s}">在此賽道中的角色（文件原文）</div>'
        f'<div style="font-size:0.93rem;color:#4A4035;'
        f'{"font-style:italic;" if is_italic else ""}line-height:1.55">'
        f'"{html_lib.escape(quote_text)}"</div>'
        f'<div style="font-size:0.76rem;color:#8A7F6E;margin-top:0.35rem">'
        f'來源：{html_lib.escape(src_label)}{html_lib.escape(src_meta)}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── 來源引用 & Google 連結 ───────────────────
    sources = brief.get("sources", [])

    def _short_src_label(s: dict, idx: int) -> str:
        """從 title 或 URI 提取簡短顯示名稱"""
        title = (s.get("title") or "").strip()
        uri   = s.get("uri", "")
        # 優先用 title（截到第一個 | 或 - 前，再截 20 字）
        if title:
            label = title.split("|")[0].split(" - ")[0].split("–")[0].strip()
            label = label[:22] + ("…" if len(label) > 22 else "")
        else:
            # fallback：用 domain
            try:
                from urllib.parse import urlparse
                label = urlparse(uri).netloc.replace("www.", "")[:22]
            except Exception:
                label = f"來源 {idx+1}"
        return label

    src_links = " · ".join(
        f'<a href="{s["uri"]}" target="_blank" style="color:#C8A96E;text-decoration:none;font-size:0.76rem">'
        f'[{i+1}] {html_lib.escape(_short_src_label(s, i))}'
        f'</a>'
        for i, s in enumerate(sources)
    ) if sources else ""

    google_q   = html_lib.escape(name).replace(" ", "+")
    google_url = f"https://www.google.com/search?q={name.replace(' ', '+')}"
    src_row = (
        f'<span style="color:#B0A890;font-size:0.76rem">⚠ AI 搜尋整理，資料僅供參考</span>'
        + (f'<br><span style="color:#8A7F6E;font-size:0.76rem">引用來源：</span>{src_links}' if src_links else "")
    )
    st.markdown(
        f'<div style="border-top:1px solid #E2DDD4;padding-top:0.75rem;margin-top:0.3rem;'
        f'display:flex;justify-content:space-between;align-items:flex-start;'
        f'flex-wrap:wrap;gap:0.5rem">'
        f'<div>{src_row}</div>'
        f'<a href="{google_url}" target="_blank" style="font-size:0.82rem;color:#4A4035;'
        f'text-decoration:none;border:1px solid #D8D0C4;border-radius:3px;'
        f'padding:4px 12px;white-space:nowrap;flex-shrink:0">🔍 Google 搜尋</a>'
        f'</div>',
        unsafe_allow_html=True
    )

# ── 書籤輔助函式 ───────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent / "data"

def _bookmarks_path(track_name: str) -> Path:
    safe = track_name.replace("/", "_").replace(" ", "_")[:40]
    return _DATA_DIR / f"bookmarks_{safe}.json"

def load_bookmarks(track_name: str) -> dict:
    p = _bookmarks_path(track_name)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_bookmarks(track_name: str, bookmarks: dict):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _bookmarks_path(track_name).write_text(
        json.dumps(bookmarks, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# ── 啟動時讀取歷史搜尋（只做一次） ───────────────────────────────────
if not st.session_state.history_loaded:
    for record in load_search_history():
        kw   = record["keyword"]
        data = record["data"]
        if kw and kw not in st.session_state.brief_cache:
            try:
                recs_data = data.get("recommendations")
                smap_data = data.get("skeleton_map")
                if recs_data:
                    st.session_state.brief_cache[kw] = {
                        "recs":   BriefRecommendations(**recs_data),
                        "track3": data.get("track3", {}),
                    }
                if smap_data:
                    st.session_state.skeleton_cache[kw] = SkeletonMap(**smap_data)
            except Exception:
                pass
    st.session_state.history_loaded = True

# ═══════════════════════════════════════════════════════════════════
# Header
# ═══════════════════════════════════════════════════════════════════
st.markdown("""
<div class="sr-header">
  <div>
    <p class="sr-eyebrow">Private Equity · Supply Chain Intelligence</p>
    <p class="sr-title">PE Sourcing Tool</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── API Key 輸入 bar（僅在無 key 時顯示）──────────────────────────
_has_key = bool(st.session_state.get("gemini_api_key", "").strip())
if not _has_key:
    _ka, _kb, _kc = st.columns([2.5, 4, 1], gap="small", vertical_alignment="center")
    with _ka:
        st.markdown(
            '<div style="background:#FDF3E0;border:1px solid #E8C87A;border-radius:4px;'
            'padding:0.52rem 0.9rem;font-size:0.74rem;color:#7A5010;white-space:nowrap">'
            '🔑 請輸入 Gemini API Key 以啟用分析功能</div>',
            unsafe_allow_html=True,
        )
    with _kb:
        _key_input = st.text_input(
            "Gemini API Key",
            type="default",
            placeholder="AIza...",
            help="前往 aistudio.google.com/apikey 取得 Gemini API Key",
            label_visibility="collapsed",
            key="api_key_text_input",
        )
    with _kc:
        if st.button("確認", key="api_key_submit", type="primary", use_container_width=True):
            if _key_input.strip():
                st.session_state["gemini_api_key"] = _key_input.strip()
                set_gemini_api_key(_key_input.strip())
                st.rerun()
            else:
                st.warning("請輸入有效的 API Key")

# ═══════════════════════════════════════════════════════════════════
# 搜尋列：關鍵字輸入 + 已存賽道 + 按鈕
# ═══════════════════════════════════════════════════════════════════
saved_tracks = load_saved_tracks()
saved_names  = [t["keyword"] for t in saved_tracks]

def _fmt_saved_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%m/%d")
    except Exception:
        return ""

# widget 建立前套用 pending 值（Streamlit 不允許 widget 建立後改同一 key）
if st.session_state.get("_pending_kw") is not None:
    st.session_state["kw_input_widget"] = st.session_state["_pending_kw"]
    st.session_state["_pending_kw"] = None
if st.session_state.get("_combo_reset_pending"):
    st.session_state["combo_sel_widget"] = 0
    st.session_state["_combo_reset_pending"] = False
if st.session_state.get("_pending_scene_ctx") is not None:
    st.session_state["scene_context"] = st.session_state["_pending_scene_ctx"]
    st.session_state["_pending_scene_ctx"] = None

c_kw, c_saved, c_gen, c_refresh = st.columns([3, 2, 1, 1], gap="small", vertical_alignment="bottom")

with c_kw:
    keyword_input = st.text_input(
        "產業 / 公司關鍵字",
        placeholder="例：半導體先進封裝、HBM、被動元件",
        key="kw_input_widget",
        help="輸入產業賽道或目標公司名稱",
    )
    # 使用者手動輸入 → 同步 active_keyword、重設下拉選單、清除 dropdown flag 與應用場景
    if keyword_input != st.session_state.get("active_keyword", ""):
        st.session_state.active_keyword = keyword_input
        st.session_state["combo_sel_widget"] = 0
        st.session_state["_kw_via_dropdown"] = False
        st.session_state["_pending_scene_ctx"] = ""
        st.session_state["_scene_chips"] = []
        st.session_state["_chips_for_kw"] = ""
        st.session_state["_scene_ctx_keyword"] = ""

with c_saved:
    # 建立合併選單：已儲存 + 最近搜尋（去重）
    _history = load_search_history()
    _seen_hist, _recent_kws = set(saved_names), []
    for _h in _history:
        _kw = _h.get("keyword", "")
        if _kw and _kw not in _seen_hist:
            _seen_hist.add(_kw)
            _recent_kws.append(_kw)
        if len(_recent_kws) >= 5:
            break

    _combo_options = [None]
    _combo_labels  = ["— 選擇已儲存關鍵字 —"]
    if saved_tracks:
        for t in saved_tracks:
            _combo_options.append(("saved", t.get("label") or t["keyword"]))
            _custom_label = t.get("label")
            if _custom_label:
                _combo_labels.append(f"★ {_custom_label}")
            else:
                _combo_labels.append(f"★ {t['keyword']}  {_fmt_saved_date(t.get('saved_at', ''))}")
    if _recent_kws:
        for _kw in _recent_kws:
            _combo_options.append(("hist", _kw))
            _combo_labels.append(f"🕐 {_kw}")

    combo_sel = st.selectbox(
        "已儲存 / 最近搜尋",
        range(len(_combo_labels)),
        format_func=lambda i: _combo_labels[i],
        key="combo_sel_widget",
    )
    if combo_sel > 0:
        selected_saved = _combo_options[combo_sel][1]
        if selected_saved != st.session_state.get("active_keyword", ""):
            st.session_state["_pending_kw"] = selected_saved
            st.session_state.active_keyword = selected_saved
            st.session_state["_combo_reset_pending"] = True
            st.session_state["_kw_via_dropdown"] = True
            st.session_state["_pending_scene_ctx"] = ""
            st.session_state["_scene_chips"] = []
            st.session_state["_chips_for_kw"] = ""
            st.session_state["_scene_ctx_keyword"] = ""
            st.rerun()


_active_kw   = st.session_state.get("active_keyword", "")
# label→keyword 反查：已改名的賽道 active_keyword 存的是 label，需還原為 keyword
_active_kw_resolved = next(
    (t["keyword"] for t in saved_tracks if t.get("label") == _active_kw),
    _active_kw,
)
_is_saved_kw = bool(_active_kw_resolved and _active_kw_resolved in saved_names)
_editing     = st.session_state.get("rename_editing", False)

# Row 2：應用場景（左）+ 按鈕（右）
_r2_ctx, _r2_btn, _r2_sp = st.columns([3, 2, 2], gap="small", vertical_alignment="center")
with _r2_ctx:
    _ctx_input_col, _ctx_suggest_col = st.columns([5, 1], gap="small", vertical_alignment="bottom")
    with _ctx_input_col:
        scene_context = st.text_input(
            "應用場景／分析角度（選填）",
            placeholder="例：AI 伺服器、車用電子",
            key="scene_context",
            help=(
                "輸入賽道關鍵字後，再補充你關注的應用方向，讓供應鏈地圖更精準。\n\n"
                "📌 範例：\n"
                "• 散熱模組 → AI 伺服器、資料中心\n"
                "• 被動元件 → 車用電子、EV 電池\n"
                "• 工業連接器 → 工廠自動化、機器人\n"
                "• 軟板（FPC）→ 手機、穿戴式裝置\n"
                "• 精密加工 → 醫療器材、航太\n\n"
                "不填則由 AI 自動判斷主要應用場景。"
            ),
        )
    with _ctx_suggest_col:
        if st.button("💡", key="suggest_chips_btn", help="根據關鍵字 AI 建議應用場景", use_container_width=True):
            _kw_for_chips = st.session_state.get("kw_input_widget", "").strip()
            if _kw_for_chips:
                _old_chip_kw = st.session_state.get("_chips_for_kw", "")
                with st.spinner(""):
                    _new_chips = suggest_scene_contexts(_kw_for_chips)
                st.session_state["_scene_chips"] = _new_chips
                st.session_state["_chips_for_kw"] = _kw_for_chips
                # 換了關鍵字才按 💡 → 舊場景已過期，清除
                if _kw_for_chips != _old_chip_kw:
                    st.session_state["_pending_scene_ctx"] = ""
                st.rerun()

with _r2_btn:
    if _is_saved_kw and _editing:
        _cur_track2 = next((t for t in saved_tracks if t["keyword"] == _active_kw_resolved), None)
        _cur_label2 = (_cur_track2.get("label") or _active_kw_resolved) if _cur_track2 else _active_kw_resolved
        _re1, _re2, _re3 = st.columns([5, 2, 2], vertical_alignment="center")
        with _re1:
            _new_label2 = st.text_input("新名稱", value=_cur_label2, key="rename_input", label_visibility="collapsed")
        with _re2:
            if st.button("確認", key="rename_confirm", use_container_width=True):
                if _new_label2.strip():
                    rename_track_label(_active_kw_resolved, _new_label2.strip())
                    st.session_state["_pending_kw"] = _new_label2.strip()
                    st.session_state.active_keyword = _new_label2.strip()
                st.session_state["rename_editing"] = False
                st.rerun()
        with _re3:
            if st.button("取消", key="rename_cancel", use_container_width=True):
                st.session_state["rename_editing"] = False
                st.rerun()
    elif _is_saved_kw:
        _rb1, _rb2 = st.columns([1, 1], gap="small")
        with _rb1:
            if st.button("✏️ 更改儲存賽道名稱", key="rename_toggle", use_container_width=True):
                st.session_state["rename_editing"] = True
                st.rerun()
        with _rb2:
            if st.button("🗑 從已儲存清單移除", key="remove_inline", use_container_width=True):
                delete_track(_active_kw_resolved)
                st.rerun()
    _active_for_save2 = next(
        (t["keyword"] for t in saved_tracks if t.get("label") == keyword_input.strip()),
        keyword_input.strip(),
    )
    if _active_for_save2 and _active_for_save2 in st.session_state.brief_cache:
        if _active_for_save2 not in saved_names:
            if st.button("⭐ 加入儲存清單", key="save_inline", use_container_width=True):
                from librarian import SEARCH_CACHE_DIR
                _safe2 = _active_for_save2.replace("/","_").replace(" ","_")[:30]
                _matches2 = sorted(SEARCH_CACHE_DIR.glob(f"{_safe2}_*.json"), reverse=True)
                save_track(_active_for_save2, _matches2[0].name if _matches2 else "")
                st.rerun()

# Row 3：Chips（獨立一行，寬度與 keyword 欄對齊）
_chips_list = st.session_state.get("_scene_chips", [])
_chips_kw   = st.session_state.get("_chips_for_kw", "")
if _chips_list and _chips_kw == st.session_state.get("kw_input_widget", "").strip():
    _chip_row, _ = st.columns([3, 4], gap="small")
    with _chip_row:
        # scene_context 只在「為當前關鍵字設定的」情況下才算有效選中
        _ctx_kw = st.session_state.get("_scene_ctx_keyword", "")
        _cur_ctx = st.session_state.get("scene_context", "").strip() if _ctx_kw == _chips_kw else ""
        _chip_btns = st.columns(len(_chips_list), gap="small")
        for _ci, _chip in enumerate(_chips_list):
            with _chip_btns[_ci]:
                _selected = _chip in _cur_ctx
                if st.button(
                    f"✓ {_chip}" if _selected else _chip,
                    key=f"chip_{_ci}",
                    type="primary" if _selected else "secondary",
                    use_container_width=True,
                ):
                    _new_ctx = ("、".join(c.strip() for c in _cur_ctx.split("、") if c.strip() != _chip)
                                if _selected else (f"{_cur_ctx}、{_chip}" if _cur_ctx else _chip))
                    st.session_state["_pending_scene_ctx"] = _new_ctx
                    st.session_state["_scene_ctx_keyword"] = _chips_kw
                    st.rerun()

# 決定當前 active_name，並從 tracks.yaml 找對應 config（含正確 tree_file）
active_name = keyword_input.strip() or ""

# 賽道切換偵測：切換時重載 per-track processed_files
if st.session_state.get("_last_active_name") != active_name:
    st.session_state["_last_active_name"] = active_name
    st.session_state.processed_files = load_processed_files(active_name) if active_name else set()

def _resolve_config(kw: str) -> dict:
    """用關鍵字或 label 找 tracks.yaml 對應 config；找不到就用預設。"""
    if not kw:
        return {}
    all_tracks = load_tracks()
    saved = load_saved_tracks()
    # 先試 label → keyword 反查
    for t in saved:
        if t.get("label") == kw:
            kw = t["keyword"]
            break
    # 完全匹配 track name
    for cfg in all_tracks.values():
        if cfg.get("name") == kw:
            return cfg
    # fallback：預設 config
    return {
        "name":            kw,
        "search_keywords": [kw],
        "file_keywords":   [kw],
        "tree_file":       f"{kw}賽道.md",
    }

active_config = _resolve_config(active_name)
# active_config["name"] 是已還原的實際 keyword（_resolve_config 內部處理 label→keyword）
_actual_kw = active_config.get("name", active_name) if active_config else active_name

_kw_via_dropdown = st.session_state.get("_kw_via_dropdown", False)

# 若 session cache 沒有此 keyword 的資料，從磁碟最新 JSON 補載一次
if _actual_kw and _actual_kw not in st.session_state.brief_cache:
    from librarian import SEARCH_CACHE_DIR
    _safe_kw = _actual_kw.replace("/", "_").replace(" ", "_").replace("\\", "_")[:30]
    _hits = sorted(SEARCH_CACHE_DIR.glob(f"{_safe_kw}_*.json"), reverse=True) if SEARCH_CACHE_DIR.exists() else []
    if _hits:
        try:
            _d = json.loads(_hits[0].read_text(encoding="utf-8"))
            _recs_d = _d.get("recommendations")
            _smap_d = _d.get("skeleton_map")
            if _recs_d:
                st.session_state.brief_cache[_actual_kw] = {
                    "recs":   BriefRecommendations(**_recs_d),
                    "track3": _d.get("track3", {}),
                }
            if _smap_d:
                st.session_state.skeleton_cache[_actual_kw] = SkeletonMap(**_smap_d)
        except Exception:
            pass

brief_loaded = bool(st.session_state.brief_cache.get(_actual_kw, {}).get("recs"))

with c_gen:
    st.markdown("<div style='margin-top:1.75rem'></div>", unsafe_allow_html=True)
    gen_btn = st.button(
        "◈ 分析賽道",
        disabled=(not active_name) or brief_loaded or not _has_key,
        use_container_width=True,
        type="primary",
        help=None if _has_key else "請先輸入 Gemini API Key",
    )

with c_refresh:
    st.markdown("<div style='margin-top:1.75rem'></div>", unsafe_allow_html=True)
    refresh_btn = st.button(
        "↺ 重新分析關鍵字",
        disabled=not brief_loaded,
        use_container_width=True,
    )


def _gemini_err_msg(e: Exception) -> str:
    """將 Gemini API 錯誤轉為使用者友善中文說明"""
    s = str(e)
    if "503" in s or "UNAVAILABLE" in s:
        return "Gemini 系統目前負載過高，請稍候片刻後點「重新分析關鍵字」再試。"
    if "429" in s or "RESOURCE_EXHAUSTED" in s:
        return "API 用量已達上限，請稍後再試。"
    if "400" in s or "INVALID_ARGUMENT" in s:
        return "請求格式有誤，請確認輸入內容後重試。"
    return f"發生錯誤，請重試。（{s[:120]}）"

# ── 觸發 ──────────────────────────────────────────────────────────
if gen_btn and active_name:
    st.session_state.active_keyword    = keyword_input.strip()
    st.session_state.active_track_name = active_name
    keywords = active_config.get("search_keywords", [_actual_kw])

    _ctx = st.session_state.get("scene_context", "").strip()
    with st.spinner("Gemini 生成供應鏈骨架地圖..."):
        try:
            smap = generate_skeleton_map(_actual_kw, context=_ctx)
            st.session_state.skeleton_cache[_actual_kw] = smap
        except Exception as e:
            st.warning(f"骨架地圖生成失敗：{_gemini_err_msg(e)}")

    with st.spinner("Gemini 分析供應鏈推薦公司中..."):
        try:
            smap_for_recs = st.session_state.skeleton_cache.get(_actual_kw)
            recs = generate_recommendations(_actual_kw, keywords, skeleton=smap_for_recs, context=_ctx)
        except Exception as e:
            st.error(f"推薦生成失敗：{_gemini_err_msg(e)}"); st.stop()

    st.session_state.brief_cache[_actual_kw] = {"recs": recs}
    st.session_state["_kw_via_dropdown"] = True
    try:    generate_research_brief(_actual_kw, active_config, recs)
    except: pass
    try:
        smap_to_save = st.session_state.skeleton_cache.get(_actual_kw)
        save_search_result(_actual_kw, smap_to_save, recs, {})
    except: pass
    st.rerun()

if refresh_btn and active_name:
    # 重新跑骨架地圖 + 推薦
    keywords = active_config.get("search_keywords", [_actual_kw])
    _ctx = st.session_state.get("scene_context", "").strip()
    with st.spinner("重新分析關鍵字，生成骨架地圖與建議..."):
        try:
            smap = generate_skeleton_map(_actual_kw, context=_ctx)
            st.session_state.skeleton_cache[_actual_kw] = smap
        except Exception as e:
            st.warning(f"骨架地圖生成失敗：{_gemini_err_msg(e)}")
        try:
            smap_for_recs = st.session_state.skeleton_cache.get(_actual_kw)
            recs = generate_recommendations(_actual_kw, keywords, skeleton=smap_for_recs, context=_ctx)
            st.session_state.brief_cache[_actual_kw] = {"recs": recs}
        except Exception as e:
            st.error(f"推薦生成失敗：{_gemini_err_msg(e)}")
    try:
        smap_to_save = st.session_state.skeleton_cache.get(_actual_kw)
        recs_to_save = st.session_state.brief_cache.get(_actual_kw, {}).get("recs")
        if smap_to_save and recs_to_save:
            save_search_result(_actual_kw, smap_to_save, recs_to_save, {})
    except: pass
    st.session_state["_kw_via_dropdown"] = True
    st.toast("關鍵字重新分析完成", icon="✅")
    st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# ── 資料取出（有快取就顯示，不限定輸入方式）────────────────────────
brief = st.session_state.brief_cache.get(_actual_kw, {})
recs  = brief.get("recs")
smap  = st.session_state.skeleton_cache.get(_actual_kw)


# ═══════════════════════════════════════════════════════════════════
# 供應鏈骨架地圖
# ═══════════════════════════════════════════════════════════════════
if smap:
    layer_cards = []
    for i, layer in enumerate(smap.layers):
        arrow = '<span class="map-arrow">→</span>' if i > 0 else ""
        name_e = html_lib.escape(layer.name)
        desc_e = html_lib.escape(layer.description)

        if layer.out_of_scope:
            companies_html = ""
            layer_class    = "map-layer scope-out"
            # 固定標題與描述，不論 Gemini 回傳什麼
            name_e = html_lib.escape("超出本系統分析涵蓋範圍")
            desc_e = html_lib.escape("涉及基礎化學品、金屬原料、精密機械零件等更上游原料供應商，資訊通常不公開或高度分散。")
        elif layer.known_companies:
            chip_parts = []
            for c in layer.known_companies:
                if c.endswith("*"):
                    # * 代表 AI 對公司名稱信心較低，以不同樣式 + tooltip 提示
                    display = html_lib.escape(c.rstrip("*"))
                    chip_parts.append(
                        f'<span class="map-co-chip" style="opacity:0.65;border-style:dashed;" '
                        f'title="AI 信心較低，請自行核對此公司名稱是否正確">{display} ·</span>'
                    )
                else:
                    chip_parts.append(f'<span class="map-co-chip">{html_lib.escape(c)}</span>')
            companies_html = "".join(chip_parts)
            layer_class    = "map-layer"
        else:
            companies_html = ""   # Layer 3 空白，不顯示任何提示
            layer_class    = "map-layer"

        layer_cards.append(
            f'{arrow}<div class="{layer_class}">'
            f'<div class="map-level">Layer {layer.level}</div>'
            f'<div class="map-layer-name">{name_e}</div>'
            f'<div class="map-layer-desc">{desc_e}</div>'
            f'{companies_html}</div>'
        )

    map_html = (
        f'<p class="map-section-label">供應鏈骨架地圖 &nbsp;·&nbsp; {html_lib.escape(active_name)}'
        f'<span style="font-size:0.7rem;color:#A09880;font-weight:400;margin-left:0.8rem">'
        f'AI 動態生成 · 每次結果可能略有不同</span></p>'
        f'<div class="map-flow">{"".join(layer_cards)}</div>'
    )
    st.markdown(map_html, unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# 三軌道
# ═══════════════════════════════════════════════════════════════════
col1, col2 = st.columns(2, gap="large")


# ── Track I ───────────────────────────────────────────────────────
with col1:
    st.markdown("""
    <div class="track-card">
      <p class="track-label">Track I</p>
      <p class="track-title">年報</p>
      <p class="track-desc">上傳大廠<strong style="color:#1A1611">年度報告（年報）</strong><br>
      系統從採購揭露條款萃取未上市供應商<br>
      <span style="font-size:0.74rem;color:#9A8A78">※ 多數上市公司年報以代號取代供應商名稱，抓到 0 筆屬正常現象</span><br>
      <span style="font-size:0.68rem;color:#C8A96E">✗ 請勿上傳財務報告或合併報表</span></p>
    </div>""", unsafe_allow_html=True)

    if recs:
        st.markdown('<p class="section-label">建議上傳公司</p>', unsafe_allow_html=True)
        st.markdown(
            '<p style="font-size:0.74rem;color:#9A8A78;margin:-0.4rem 0 0.5rem">'
            '以下為 AI 建議，亦可自行上傳其他公司年報</p>',
            unsafe_allow_html=True
        )
        for c in recs.track1:
            _uploaded = c.company_name in st.session_state.uploaded_companies
            _done_badge = (
                '<span style="font-size:0.65rem;color:#3A6B3A;background:#E8F0E8;'
                'border-radius:2px;padding:1px 5px;margin-left:5px;vertical-align:middle">✓ 已上傳</span>'
            ) if _uploaded else ""
            st.markdown(f"""
            <div class="rec-item">
              <span class="rec-ticker">{c.ticker}</span>
              <div>
                <div class="rec-name">{c.company_name}{_done_badge}</div>
                <div class="rec-reason">{c.reason}</div>
              </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<p style="font-size:0.74rem;color:#8A7F6E;margin-top:0.4rem">輸入關鍵字並分析賽道以取得建議清單</p>', unsafe_allow_html=True)

    st.markdown('<p class="section-label" style="margin-top:1.1rem">上傳年報 PDF</p>', unsafe_allow_html=True)
    uploaded_t1 = st.file_uploader(
        "年報",
        type=["pdf", "txt"],
        key=f"t1_{active_name}",
        label_visibility="collapsed",
        help="上傳年度報告（Annual Report）PDF，可一次選取多份",
        accept_multiple_files=True,
    )
    if uploaded_t1:
        done    = [f for f in uploaded_t1 if f"t1::{f.name}" in st.session_state.processed_files]
        pending = [f for f in uploaded_t1 if f"t1::{f.name}" not in st.session_state.processed_files]
        if done:
            st.success(f"✓ 已完成 {len(done)} 份：{', '.join(f.name for f in done)}")
        if pending:
            st.caption(f"📄 待分析 {len(pending)} 份：{', '.join(f.name for f in pending)}")

# ── Track II ──────────────────────────────────────────────────────
with col2:
    st.markdown("""
    <div class="track-card">
      <p class="track-label">Track II</p>
      <p class="track-title">合併財報</p>
      <p class="track-desc">上傳大廠<strong style="color:#1A1611">合併財務報告</strong><br>
      從附表九／附表六萃取被投資未上市公司<br>
      <span style="font-size:0.74rem;color:#9A8A78"> </span><br>
      <span style="font-size:0.68rem;color:#C8A96E">✗ 請勿上傳年報或 CSR 報告</span></p>
    </div>""", unsafe_allow_html=True)

    if recs:
        st.markdown('<p class="section-label">建議上傳公司</p>', unsafe_allow_html=True)
        st.markdown(
            '<p style="font-size:0.74rem;color:#9A8A78;margin:-0.4rem 0 0.5rem">'
            '以下為 AI 建議，亦可自行上傳其他公司合併財報</p>',
            unsafe_allow_html=True
        )
        for c in recs.track2:
            _uploaded2 = c.company_name in st.session_state.uploaded_companies
            _done_badge2 = (
                '<span style="font-size:0.65rem;color:#3A6B3A;background:#E8F0E8;'
                'border-radius:2px;padding:1px 5px;margin-left:5px;vertical-align:middle">✓ 已上傳</span>'
            ) if _uploaded2 else ""
            st.markdown(f"""
            <div class="rec-item">
              <span class="rec-ticker">{c.ticker}</span>
              <div>
                <div class="rec-name">{c.company_name}{_done_badge2}</div>
                <div class="rec-reason">{c.reason}</div>
              </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<p style="font-size:0.74rem;color:#8A7F6E;margin-top:0.4rem">輸入關鍵字並分析賽道以取得建議清單</p>', unsafe_allow_html=True)

    st.markdown('<p class="section-label" style="margin-top:1.1rem">上傳合併財報 PDF</p>', unsafe_allow_html=True)
    uploaded_t2 = st.file_uploader(
        "合併財報",
        type=["pdf"],
        key=f"t2_{active_name}",
        label_visibility="collapsed",
        help="上傳合併財務報告 PDF（需含附表九），可一次選取多份",
        accept_multiple_files=True,
    )
    if uploaded_t2:
        done    = [f for f in uploaded_t2 if f"t2::{f.name}" in st.session_state.processed_files]
        pending = [f for f in uploaded_t2 if f"t2::{f.name}" not in st.session_state.processed_files]
        if done:
            st.success(f"✓ 已完成 {len(done)} 份：{', '.join(f.name for f in done)}")
        if pending:
            st.caption(f"📄 待分析 {len(pending)} 份：{', '.join(f.name for f in pending)}")

# ── 分析按鈕 + 重新分析────────────────────────────────────────────
pending_t1 = [f for f in (uploaded_t1 or []) if f"t1::{f.name}" not in st.session_state.processed_files]
pending_t2 = [f for f in (uploaded_t2 or []) if f"t2::{f.name}" not in st.session_state.processed_files]

# 重新分析：顯示當前賽道的已儲存 PDF
_track_pdf_dir = get_track_pdf_dir(active_name) if active_name else None
existing_pdfs = sorted(_track_pdf_dir.glob("*.pdf")) if (_track_pdf_dir and _track_pdf_dir.exists()) else []
_keep_expander = st.session_state.pop("_pdf_expander_open", False)
_src_type_map = load_file_source_types(active_name)

if existing_pdfs:
    with st.expander(f"📁 已儲存 {len(existing_pdfs)} 份 PDF", expanded=_keep_expander):
        for p in existing_pdfs:
            _stype = _src_type_map.get(p.name, "")
            _stype_label = {"Annual_Report": "T1", "Financial_Statement": "T2"}.get(_stype, "?")
            col_name, col_rerun, col_del = st.columns([8, 2, 1])
            with col_name:
                st.caption(f"· [{_stype_label}] {p.name}  ({p.stat().st_size // 1024} KB)")
            with col_rerun:
                if st.button("↺ 重跑", key=f"rerun_{p.name}", help="單獨重新分析此檔案"):
                    st.session_state["_pending_rerun_pdf"] = str(p)
                    st.session_state["_pdf_expander_open"] = True
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del_{p.name}", help=f"移除 {p.name} 並清除其萃取結果"):
                    # 刪除 PDF 檔
                    p.unlink()
                    # 同步清除此 PDF 在 tree 中的舊結果
                    _tree_file_del = (
                        TRACK_TREES_DIR / _resolve_config(active_name).get(
                            "tree_file", f"{active_name}賽道.md"
                        )
                        if active_name else None
                    )
                    if _tree_file_del and _tree_file_del.exists():
                        _details_del = _tree_file_del.with_name(
                            _tree_file_del.stem + "_details.json"
                        )
                        _del_src = None
                        if _details_del.exists():
                            try:
                                import json as _json2
                                _drecs = _json2.loads(_details_del.read_text(encoding="utf-8"))
                                _dcands = [
                                    r.get("source_company", "")
                                    for r in _drecs
                                    if r.get("source_pdf") == p.name
                                ]
                                if _dcands:
                                    from collections import Counter as _C2
                                    _del_src = _C2(_dcands).most_common(1)[0][0]
                            except Exception:
                                pass
                        if _del_src:
                            purge_source_from_tree(_del_src, _tree_file_del)
                    st.session_state["_pdf_expander_open"] = True
                    st.toast(f"已移除：{p.name} 及其萃取結果", icon="🗑")
                    st.rerun()
        st.divider()
        if st.button("↺ 全部重新分析", use_container_width=True):
            st.session_state["_pending_rerun_pdf"] = "ALL"
            st.session_state["_pdf_expander_open"] = True
            st.rerun()

# ── 單筆 / 全部重跑（expander 外執行，避免 Streamlit block 問題）──────
_pending_rerun = st.session_state.pop("_pending_rerun_pdf", None)
if _pending_rerun and active_name and _track_pdf_dir:
    _rerun_tracks = load_tracks()
    if _pending_rerun == "ALL":
        st.session_state.processed_files.clear()
        save_processed_files(set(), active_name)
        _rerun_list = existing_pdfs
    else:
        _rerun_list = [Path(_pending_rerun)]
    _active_config_rerun = _resolve_config(active_name)
    _tree_file_rerun = (
        TRACK_TREES_DIR / _active_config_rerun.get("tree_file", f"{active_name}賽道.md")
        if _active_config_rerun else None
    )
    for _rpdf in _rerun_list:
        _rstype = _src_type_map.get(_rpdf.name)
        with st.spinner(f"重新分析：{_rpdf.name}…"):
            try:
                # ① 先清除此 PDF 舊結果（以 source_company 為 key，從 tree 中移除）
                # 用 _details.json 找此 PDF 對應的 source_company 名稱
                if _tree_file_rerun and _tree_file_rerun.exists():
                    _details_file = _tree_file_rerun.with_name(
                        _tree_file_rerun.stem + "_details.json"
                    )
                    _old_src = None
                    if _details_file.exists():
                        try:
                            import json as _json
                            _details = _json.loads(_details_file.read_text(encoding="utf-8"))
                            # source_pdf 精確比對：找不到就不清除，絕不猜測
                            _pdf_matches = [
                                r.get("source_company", "")
                                for r in _details
                                if r.get("source_pdf") == _rpdf.name
                            ]
                            if _pdf_matches:
                                from collections import Counter as _Counter
                                _old_src = _Counter(_pdf_matches).most_common(1)[0][0]
                        except Exception:
                            pass
                    if _old_src:
                        _purged = purge_source_from_tree(_old_src, _tree_file_rerun)
                        if _purged:
                            st.caption(f"↩ 已清除 {_old_src} 舊資料（{_purged} 筆）")

                # ② 重新分析（傳入使用者選定的賽道，避免 Gemini 自判跑錯 tree）
                result = process_file(_rpdf, _rerun_tracks, source_type=_rstype, target_track_name=active_name or None)
                src_co, count = result if result else (None, 0)
                st.session_state.processed_files.add(f"rerun::{_rpdf.name}")
                if count > 0:
                    st.toast(f"✓ {_rpdf.name}　抓到 {count} 筆", icon="✅")
                else:
                    st.toast(f"⚠ {_rpdf.name}　抓到 0 筆", icon="⚠️")
            except Exception as e:
                st.error(f"重跑失敗 {_rpdf.name}：{e}")

if pending_t1 or pending_t2:
    total = len(pending_t1) + len(pending_t2)
    btn_label = f"▶ 開始分析（共 {total} 份）"
    if st.button(btn_label, type="primary", use_container_width=False,
                 disabled=not _has_key,
                 help=None if _has_key else "請先輸入 Gemini API Key"):
        _track_pdf_dir.mkdir(parents=True, exist_ok=True)
        for uf in pending_t1:
            with st.spinner(f"T1 分析中：{uf.name}..."):
                try:
                    sp = _track_pdf_dir / uf.name
                    if not sp.exists():
                        sp.write_bytes(uf.read())
                    src, count = process_file(sp, load_tracks(), source_type="Annual_Report", target_track_name=active_name or None)
                    if src:
                        st.session_state.uploaded_companies.add(src)
                    st.session_state.processing_log.append(
                        f"[{datetime.now().strftime('%H:%M')}] T1：{uf.name}"
                    )
                    save_file_source_type(uf.name, "Annual_Report", active_name)
                    if count > 0:
                        st.session_state.processed_files.add(f"t1::{uf.name}")
                        save_processed_files(st.session_state.processed_files, active_name)
                        st.success(f"✓ T1 完成：{uf.name}　抓到 {count} 筆")
                    else:
                        st.warning(f"⚠ T1：{uf.name}　未抓到具名供應商（正常現象，詳見說明）")
                except Exception as e:
                    st.error(f"T1 失敗 {uf.name}：{e}")
        for uf in pending_t2:
            with st.spinner(f"T2 分析中：{uf.name}..."):
                try:
                    sp = _track_pdf_dir / uf.name
                    if not sp.exists():
                        sp.write_bytes(uf.read())
                    src, count = process_file(sp, load_tracks(), source_type="Financial_Statement", target_track_name=active_name or None)
                    if src:
                        st.session_state.uploaded_companies.add(src)
                    st.session_state.processing_log.append(
                        f"[{datetime.now().strftime('%H:%M')}] T2：{uf.name}"
                    )
                    save_file_source_type(uf.name, "Financial_Statement", active_name)
                    if count > 0:
                        st.session_state.processed_files.add(f"t2::{uf.name}")
                        save_processed_files(st.session_state.processed_files, active_name)
                        st.success(f"✓ T2 完成：{uf.name}　抓到 {count} 筆")
                    else:
                        st.warning(f"⚠ T2：{uf.name}　抓到 0 筆，可重新上傳再試")
                except Exception as e:
                    st.error(f"T2 失敗 {uf.name}：{e}")
        st.rerun()


# ═══════════════════════════════════════════════════════════════════
# 已發現公司
# ═══════════════════════════════════════════════════════════════════
st.markdown("<hr>", unsafe_allow_html=True)

tree_file = TRACK_TREES_DIR / active_config.get("tree_file", f"{active_name}賽道.md") if active_config else None

# 載入詳細資料 JSON（供公司簡介卡片使用）
details_map: dict = load_company_details(tree_file) if tree_file else {}

if tree_file and tree_file.exists():
    content = tree_file.read_text(encoding="utf-8")
    rows = []
    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|")[1:-1]]
        if len(cols) < 6:
            continue
        if cols[0] in ("公司名", "--------", "---") or cols[0].startswith("---"):
            continue
        # 即時重查上市狀態（修正舊資料的錯誤值）
        clean = _re.sub(r'\s*\[産業補助 TIIP \d*\]', '', cols[0]).strip()
        fresh_status = get_listing_status(clean)
        if len(cols) > 2:
            cols[2] = fresh_status
        rows.append(cols)

    def _clean_name(raw: str) -> str:
        return _re.sub(r'\s*\[産業補助 TIIP \d*\]', '', raw).strip()

    # ── 去重：同公司名保留最後一筆（最新上傳的資料）────────────────
    _dedup: dict = {}
    for r in rows:
        _dedup[_clean_name(r[0])] = r
    rows = list(_dedup.values())

    # ── 規則過濾：刷掉明確無關項目 ──────────────────────────────
    _NOISE_DESC = ["社會工作服務", "出租攤位", "辦公大樓", "不動產租賃", "專業性投資活動",
                   "國際貿易", "銀行服務", "證券服務", "保險服務", "金融服務",
                   "對各種事業之投資", "轉投資事業", "股權投資", "創業投資",
                   "營造工程", "建築設計", "土木工程", "工程顧問", "室內設計"]
    _NOISE_NAME = ["社會企業", "基金會", "貿易", "法律事務所", "會計師事務所",
                   "廣告", "公關", "建築師事務所", "營造"]
    _FINANCIAL_KW = ["銀行", "證券", "保險", "投信", "票券", "金控", "租賃金融",
                     "商業銀行", "法律事務所", "會計師事務所"]

    # 產品代碼後綴：公司名結尾出現這些 → 可能是產品線名稱，非獨立公司
    _PRODUCT_CODE_RE = _re.compile(
        r'(CO2|N2|O2|H2|SiC|GaN|SF6|NH3|HF|H2O2|CMP|CVD|ALD|EUV|DUV|[A-Z]{2,4}\d*)\s*$'
    )

    def _is_noise(cols: list) -> bool:
        name = _clean_name(cols[0]) if cols else ""
        desc = cols[1] if len(cols) > 1 else ""
        if len(name) <= 1:
            return True
        # 外國公司（含日/韓/大陸/全英文）
        if is_foreign_company(name):
            return True
        # 產品代碼混入公司名（如「崇越CO2」）
        if _PRODUCT_CODE_RE.search(name):
            return True
        if any(kw in desc for kw in _NOISE_DESC):
            return True
        if any(kw in name for kw in _NOISE_NAME):
            return True
        if any(kw in name for kw in _FINANCIAL_KW):
            return True
        # 純投資公司：名稱去掉法律後綴後結尾是「投資」（如「測冠投資」「OO投資」）
        _core = name.replace("股份有限公司", "").replace("有限公司", "").strip()
        if _core.endswith("投資"):
            return True
        # 自我參照過濾：entity 名稱是 source 公司名稱的子集
        # 例：source=日月光投資控股，entity=日月光 → 過濾
        _source = cols[5] if len(cols) > 5 else ""
        _src_core = _source.replace("股份有限公司", "").replace("有限公司", "").strip()
        if _src_core and len(_core) >= 2 and _core in _src_core:
            return True
        return False

    rows = [r for r in rows if not _is_noise(r)]

    # ── 多來源計數：每家公司出現在幾份來源文件 ──────────────────
    source_count: dict = {}
    for r in rows:
        nm = _clean_name(r[0])
        src = r[5] if len(r) > 5 else ""
        source_count.setdefault(nm, set()).add(src)

    # 排序：來源數 × 2 + 業務描述含賽道關鍵字 + 自有 confidence
    _track_kws = active_config.get("search_keywords", [active_name]) if active_config else [active_name]

    def _score(r: list) -> int:
        nm   = _clean_name(r[0])
        desc = r[1] if len(r) > 1 else ""
        s    = len(source_count.get(nm, set())) * 2
        if any(kw in desc for kw in _track_kws) or (active_name and active_name in desc):
            s += 1
        return s

    rows.sort(key=lambda r: -_score(r))

    # ── 統計數字 ─────────────────────────────────────────────────
    multi_src_set = {nm for nm, srcs in source_count.items() if len(srcs) >= 2}

    # ── 載入書籤 ────────────────────────────────────────────────
    bookmarks = load_bookmarks(active_name) if active_name else {}

    # ── 標題列 + 清除 + CSV + 書籤匯出 ─────────────────────────────
    col_title, col_clear, col_dl, col_bm = st.columns([5, 1, 1, 1])
    with col_title:
        st.markdown('<p class="discovery-title">已發現潛在目標</p>', unsafe_allow_html=True)
    with col_clear:
        st.markdown("<div style='margin-top:1.75rem'></div>", unsafe_allow_html=True)
        if not st.session_state.get("_clear_confirm"):
            if st.button("🗑 清除", key="clear_tree", help="清除目前賽道的所有已發現公司", use_container_width=True):
                st.session_state["_clear_confirm"] = True
                st.rerun()
        else:
            st.markdown(
                '<div style="font-size:0.72rem;color:#A04020;font-weight:500;'
                'margin-bottom:0.3rem">確認清除潛在目標名單？</div>',
                unsafe_allow_html=True
            )
            _cc1, _cc2 = st.columns(2, gap="small")
            with _cc1:
                if st.button("確認清除", key="clear_confirm_yes", type="primary", use_container_width=True):
                    if tree_file and tree_file.exists():
                        tree_file.unlink()
                    details_file = tree_file.with_name(tree_file.stem + "_details.json") if tree_file else None
                    if details_file and details_file.exists():
                        details_file.unlink()
                    st.session_state["_clear_confirm"] = False
                    st.toast("已清除發現列表，請重新上傳 PDF", icon="🗑")
                    st.rerun()
            with _cc2:
                if st.button("取消", key="clear_confirm_no", use_container_width=True):
                    st.session_state["_clear_confirm"] = False
                    st.rerun()
    with col_dl:
        st.markdown("<div style='margin-top:1.75rem'></div>", unsafe_allow_html=True)
        # UTF-8-BOM：Excel 直接開中文不亂碼
        buf = io.BytesIO()
        buf.write(b"\xef\xbb\xbf")  # BOM
        import codecs
        wrapper = codecs.getwriter("utf-8")(buf)
        w = csv.writer(wrapper)
        w.writerow(["公司名", "業務描述", "上市狀態", "來源軌道", "關係類型", "關係對象"])
        for r in rows:
            w.writerow([_clean_name(r[0])] + (r[1:6] if len(r) >= 6 else r[1:]))
        st.download_button(
            "⬇ CSV", buf.getvalue(),
            file_name=f"{active_name}_發現公司.csv",
            mime="text/csv;charset=utf-8-sig", use_container_width=True
        )
    with col_bm:
        st.markdown("<div style='margin-top:1.75rem'></div>", unsafe_allow_html=True)
        # 只匯出已書籤的公司
        bm_rows = [r for r in rows if _clean_name(r[0]) in bookmarks]
        if bm_rows:
            bm_buf = io.BytesIO()
            bm_buf.write(b"\xef\xbb\xbf")
            import codecs as _codecs
            bm_wrapper = _codecs.getwriter("utf-8")(bm_buf)
            bm_w = csv.writer(bm_wrapper)
            bm_w.writerow(["公司名", "業務描述", "上市狀態", "來源軌道", "關係類型", "關係對象"])
            for r in bm_rows:
                bm_w.writerow([_clean_name(r[0])] + (r[1:6] if len(r) >= 6 else r[1:]))
            st.download_button(
                "★ 追蹤清單", bm_buf.getvalue(),
                file_name=f"{active_name}_追蹤清單.csv",
                mime="text/csv;charset=utf-8-sig",
                help=f"匯出 {len(bm_rows)} 家已加星標的公司",
                use_container_width=True
            )
        else:
            st.button("★ 追蹤清單", disabled=True, help="尚無加星標的公司", use_container_width=True)

    # ── Summary banner ───────────────────────────────────────────
    bookmark_count = len(bookmarks)
    banner_parts = [f'<span style="font-size:0.78rem;color:#6B6254">共 <strong>{len(rows)}</strong> 筆</span>']
    if multi_src_set:
        banner_parts.append(
            f'<span style="font-size:0.78rem;color:#8A6020">'
            f'▲ <strong>{len(multi_src_set)}</strong> 家多文件交叉驗證</span>'
        )
    if bookmark_count:
        banner_parts.append(
            f'<span style="font-size:0.78rem;color:#7A4A80">'
            f'★ <strong>{bookmark_count}</strong> 家追蹤中</span>'
        )
    st.markdown(
        '<div style="display:flex;gap:1.5rem;margin:0.3rem 0 0.6rem;flex-wrap:wrap">'
        + "".join(banner_parts) + "</div>",
        unsafe_allow_html=True
    )

    # ── 搜尋 + 篩選 ──────────────────────────────────────────────
    f1, f2, f3 = st.columns([4, 1.5, 1.5])
    with f1:
        search_kw = st.text_input(
            "", placeholder="搜尋公司名稱或業務描述…",
            label_visibility="collapsed", key="disc_search"
        )
    with f2:
        src_filter = st.multiselect(
            "", ["Track 1", "Track 2"], default=["Track 1", "Track 2"],
            placeholder="來源軌道", label_visibility="collapsed", key="disc_src"
        )
    with f3:
        st.markdown("<div style='margin-top:0.35rem'></div>", unsafe_allow_html=True)
        bookmark_only = st.toggle(
            f"★ 只看追蹤清單", value=False, key="bookmark_filter"
        )

    # 套用篩選
    filtered_rows = rows
    if search_kw:
        kw_lo = search_kw.lower()
        filtered_rows = [
            r for r in filtered_rows
            if kw_lo in _clean_name(r[0]).lower()
            or (len(r) > 1 and kw_lo in r[1].lower())
        ]
    if src_filter and set(src_filter) != {"Track 1", "Track 2"}:
        _src_map = {"Track 1": "T1", "Track 2": "T2"}
        _allowed = {_src_map[s] for s in src_filter if s in _src_map}
        filtered_rows = [r for r in filtered_rows if len(r) > 3 and r[3] in _allowed]
    if bookmark_only:
        filtered_rows = [r for r in filtered_rows if _clean_name(r[0]) in bookmarks]

    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin:0.2rem 0 0.5rem">'
        f'<p class="discovery-meta" style="margin:0">{len(filtered_rows)} 筆顯示 · {tree_file.name}</p>'
        f'<span style="font-size:0.72rem;color:#B0A890;letter-spacing:0.04em">'
        f'⚠ AI 萃取資料，上市狀態與業務描述請再次核實查驗</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── T1 無結果提示 ─────────────────────────────────────────────
    t1_rows = [r for r in rows if len(r) > 3 and r[3] == "T1"]
    t2_rows = [r for r in rows if len(r) > 3 and r[3] == "T2"]
    if len(t1_rows) == 0 and len(t2_rows) > 0:
        # 有 T2 結果但 T1 完全空白
        st.info(
            "ℹ️ **軌道一（年報）未抓到具名供應商，屬正常現象。**  \n"
            "台灣上市公司在年報中並無義務公開具體供應商名稱——供應商資訊若以「A廠商」代號、"
            "地區概述（台灣、日本）或百分比帶過，系統將無法辨識具體公司名稱，屬正常揭露慣例。  \n"
            "**建議以軌道二（合併財報附表）作為主要資料來源**，被投資公司名稱有法定揭露義務，資訊完整度顯著較高。"
        )
    elif len(t1_rows) == 0 and len(t2_rows) == 0 and len(rows) == 0 and tree_file.exists():
        # 所有 PDF 均無結果
        st.warning(
            "⚠️ **已處理的文件中未發現任何公司資訊。**  \n"
            "可能原因：①年報以代號或地區替代供應商名稱（常見作法）　②財報無附表被投資公司　③文件為掃描版 PDF（無法讀取文字）  \n"
            "建議確認 PDF 為可複製文字版本，或優先改用軌道二上傳合併財報。"
        )

    # ── 分頁 ────────────────────────────────────────────────────
    PAGE_SIZE = 50
    total_pages = max(1, (len(filtered_rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    pg_key = f"pg_{active_name}_{search_kw}_{src_filter}"
    if st.session_state.get("_pg_key") != pg_key:
        st.session_state["_pg_key"] = pg_key
        st.session_state["table_page"] = 0
    cur_page = max(0, min(st.session_state.get("table_page", 0), total_pages - 1))
    page_rows = filtered_rows[cur_page * PAGE_SIZE : (cur_page + 1) * PAGE_SIZE]

    # ── 表格 ────────────────────────────────────────────────────
    STATUS_COLOR = {
        "上市":  ("#E8F0E8", "#2A5A2A"),
        "上櫃":  ("#E8EAF4", "#2A3A7A"),
        "興櫃":  ("#FDF3E0", "#7A4A10"),
        "未上市": ("#F0F0F0", "#4A4A4A"),
    }

    _NO_DESC = ("業務不明", "未知", "", "年報中未明確描述")
    _NO_DESC_DISPLAY = "文件未揭露業務描述"

    def _desc_cell(desc: str) -> str:
        if desc in _NO_DESC:
            return (
                f'<span style="color:#B0A890;font-style:italic;font-size:0.82rem">'
                f'{_NO_DESC_DISPLAY}</span>'
            )
        return html_lib.escape(desc)

    def status_badge(status: str) -> str:
        bg, fg = STATUS_COLOR.get(status, ("#F0F0F0", "#4A4A4A"))
        return (
            f'<span style="display:inline-block;font-size:0.65rem;font-weight:500;'
            f'background:{bg};color:{fg};border-radius:2px;padding:1px 6px;white-space:nowrap">'
            f'{html_lib.escape(status)}</span>'
        )

    # ── 平面表格：header（HTML）+ 每行 [★按鈕 | HTML資料] ──────────
    _TH = "flex:0 0 {w}%;font-size:0.72rem;font-weight:500;color:#6B6254;letter-spacing:0.06em;text-transform:uppercase"
    _TD = "flex:0 0 {w}%;font-size:0.86rem;color:#4A4035;word-break:break-word;padding-right:6px"

    if not page_rows:
        st.markdown('<p style="font-size:0.78rem;color:#8A7F6E;margin-top:0.4rem">尚無記錄，上傳年報或財報後將自動更新</p>', unsafe_allow_html=True)
    else:
        # Header
        _, hd, _bh = st.columns([0.03, 0.92, 0.05])
        with hd:
            st.markdown(
                f'<div style="display:flex;padding:6px 2px;border-bottom:2px solid #C8A96E">'
                f'<span style="{_TH.format(w=20)}">公司名</span>'
                f'<span style="{_TH.format(w=30)}">業務描述</span>'
                f'<span style="{_TH.format(w=9)}">狀態</span>'
                f'<span style="{_TH.format(w=7)}">軌道</span>'
                f'<span style="{_TH.format(w=11)}">關係類型</span>'
                f'<span style="{_TH.format(w=23)}">關係對象</span>'
                f'</div>',
                unsafe_allow_html=True
            )

        # Rows
        for i, cols in enumerate(page_rows):
            raw_name   = cols[0] if cols else ""
            clean_name = _clean_name(raw_name)
            src_cnt    = len(source_count.get(clean_name, set()))
            is_bk      = clean_name in bookmarks
            bg         = "#FDFBF7" if i % 2 == 0 else "#F5F1EB"

            multi_html = (
                f'<span style="font-size:0.58rem;background:#FDF3E0;color:#8A6020;'
                f'border-radius:2px;padding:1px 4px;margin-left:3px;vertical-align:middle" '
                f'title="{src_cnt} 份文件交叉驗證">×{src_cnt}</span>'
            ) if src_cnt >= 2 else ""

            status_str = cols[2] if len(cols) > 2 else ""
            status_html = status_badge(status_str)

            desc_raw     = cols[1] if len(cols) > 1 else ""
            _desc_empty  = desc_raw in _NO_DESC
            desc_display = _NO_DESC_DISPLAY if _desc_empty else desc_raw
            desc_color   = "#B0A890" if _desc_empty else "#4A4035"

            _is_manual = (cols[3] if len(cols) > 3 else "") == "手動"
            if _is_manual:
                c_star, c_data, c_brief, c_del = st.columns([0.03, 0.87, 0.05, 0.05])
            else:
                c_star, c_data, c_brief = st.columns([0.03, 0.92, 0.05])
                c_del = None
            with c_star:
                if st.button("★" if is_bk else "☆", key=f"star_{cur_page}_{i}",
                             help="加入／移除追蹤清單"):
                    if is_bk:
                        bookmarks.pop(clean_name, None)
                        st.toast(f"移除追蹤：{clean_name}", icon="⭐")
                    else:
                        bookmarks[clean_name] = {
                            "desc": desc_raw,
                            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                        }
                        st.toast(f"加入追蹤：{clean_name}", icon="⭐")
                    save_bookmarks(active_name, bookmarks)
                    st.rerun()
            with c_data:
                st.markdown(
                    f'<div style="display:flex;padding:7px 2px;border-bottom:1px solid #E2DDD4;'
                    f'background:{bg};align-items:flex-start;pointer-events:none">'
                    f'<span style="{_TD.format(w=20)}">'
                    f'{html_lib.escape(clean_name)}{multi_html}</span>'
                    f'<span style="{_TD.format(w=30)};color:{desc_color};font-style:{"italic" if _desc_empty else "normal"}">'
                    f'{html_lib.escape(desc_display)}</span>'
                    f'<span style="{_TD.format(w=9)}">{status_html}</span>'
                    f'<span style="{_TD.format(w=7)};color:#6B6254">'
                    f'{html_lib.escape(cols[3] if len(cols) > 3 else "")}</span>'
                    f'<span style="{_TD.format(w=11)};color:#6B6254">'
                    f'{html_lib.escape(cols[4] if len(cols) > 4 else "")}</span>'
                    f'<span style="{_TD.format(w=23)};color:#8A7F6E">'
                    f'{html_lib.escape(cols[5] if len(cols) > 5 else "")}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            with c_brief:
                if st.button(
                    "簡介",
                    key=f"brief_{cur_page}_{i}",
                    help=(
                        "由 AI 搜尋公開資源，提供該公司的基礎簡介，"
                        "包含業務概述、主要產品、客戶群、規模與成立年份。"
                        "資料僅供參考，建議自行核實。"
                    ),
                ):
                    st.session_state["_card_info"] = {
                        "name":           clean_name,
                        "details":        details_map.get(clean_name, {}),
                        "source_company": cols[5] if len(cols) > 5 else "",
                        "track":          cols[3] if len(cols) > 3 else "",
                    }
                    _show_company_card()
            if c_del is not None:
                with c_del:
                    if st.button("🗑", key=f"del_manual_{cur_page}_{i}",
                                 help=f"刪除手動新增的「{clean_name}」"):
                        delete_manual_entry(clean_name, tree_file)
                        st.toast(f"已刪除：{clean_name}", icon="🗑")
                        st.rerun()

    # 換頁控制
    if total_pages > 1:
        # 空白欄在首末，讓按鈕不落在 first-child / last-child，
        # 避免星號按鈕 CSS 和簡介按鈕 CSS 誤套用造成兩側樣式不一致
        _sp1, p1, p2, p3, _sp2 = st.columns([0.5, 1, 4, 1, 0.5])
        with p1:
            if st.button("← 上一頁", disabled=cur_page == 0, key="pg_prev"):
                st.session_state["table_page"] = cur_page - 1
                st.rerun()
        with p2:
            st.markdown(
                f"<p style='text-align:center;font-size:0.74rem;color:#8A7F6E;margin-top:0.5rem'>"
                f"第 {cur_page + 1} 頁 / 共 {total_pages} 頁</p>",
                unsafe_allow_html=True
            )
        with p3:
            if st.button("下一頁 →", disabled=cur_page >= total_pages - 1, key="pg_next"):
                st.session_state["table_page"] = cur_page + 1
                st.rerun()


else:
    st.markdown("""
    <p class="discovery-title">已發現的未上市公司</p>
    <p style="font-size:0.78rem;color:#8A7F6E;margin-top:0.3rem">
      尚無記錄，上傳年報或財報後將自動更新</p>
    """, unsafe_allow_html=True)

# ── 手動新增公司 ──────────────────────────────────────────────────
if active_name and tree_file:
    with st.expander("＋ 手動新增公司", expanded=False):
        _m1, _m2 = st.columns([3, 2], gap="small")
        with _m1:
            _manual_name = st.text_input(
                "公司名稱", placeholder="例：信越化學、日本信越石英株式會社",
                key="manual_company_name"
            )
            _manual_desc = st.text_input(
                "業務描述（選填）", placeholder="例：生產晶圓廠製程用石英器具",
                key="manual_company_desc"
            )
        with _m2:
            _manual_rel = st.selectbox(
                "關係類型（選填）",
                ["供應商", "被投資公司", "合作廠商", "原料廠商"],
                key="manual_company_rel"
            )
            _manual_src = st.text_input(
                "關係對象（選填）", placeholder="例：崇越科技股份有限公司",
                key="manual_company_src"
            )
        if st.button("確認新增", key="manual_add_btn", type="primary"):
            if _manual_name.strip():
                ok = manual_add_to_tree(
                    entity_name=_manual_name.strip(),
                    tree_file=tree_file,
                    business_description=_manual_desc.strip(),
                    relation_category=_manual_rel,
                    source_company=_manual_src.strip(),
                )
                if ok:
                    st.toast(f"已新增：{_manual_name.strip()}", icon="✅")
                    st.rerun()
            else:
                st.warning("請輸入公司名稱")

# 近期紀錄
if st.session_state.processing_log:
    with st.expander("近期處理紀錄", expanded=False):
        for entry in st.session_state.processing_log[-10:][::-1]:
            st.caption(entry)

# Footer
st.markdown("""
<div style="margin-top:3rem;padding-top:1rem;border-top:1px solid #E2DDD4;
            font-size:0.62rem;color:#B0A890;letter-spacing:0.08em;text-align:right">
  SECTOR RADAR &nbsp;·&nbsp; POWERED BY GEMINI 2.5 FLASH
</div>
""", unsafe_allow_html=True)
