from __future__ import annotations

import base64
import csv
import html
import io
import json
import os
import re
import tempfile
import time
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import pandas as pd
import requests
import streamlit as st
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


st.set_page_config(
    page_title="B tv+ max 콘텐츠 경쟁력 비교",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_TITLE = "B tv+ max 콘텐츠 경쟁력 비교 대시보드"
BUILD_LABEL = "v17 · 정액제 건수 검증형"
BASE_DIR = Path(__file__).resolve().parent
LOCAL_DATA_PATH = BASE_DIR / "btv_max_contents.csv"
LOCAL_HISTORY_PATH = BASE_DIR / "btv_max_history.csv"

OTT_COLUMNS = {
    "넷플릭스": "netflix",
    "쿠팡플레이": "coupang",
    "티빙": "tving",
    "웨이브": "wavve",
    "디즈니+": "disney",
    "왓챠": "watcha",
}

DATA_COLUMNS = [
    "id",
    "title",
    "poster_url",
    "btv_update_date",
    "content_type",
    "open_year",
    "matched_title",
    "matched_year",
    "source_url",
    "netflix",
    "coupang",
    "tving",
    "wavve",
    "disney",
    "watcha",
    "other_providers",
    "lookup_status",
    "last_checked",
]

HISTORY_COLUMNS = [
    "history_id",
    "timestamp",
    "action",
    "row_id",
    "title",
    "btv_update_date",
    "content_type",
    "open_year",
    "poster_url",
    "source_url",
    "netflix",
    "coupang",
    "tving",
    "wavve",
    "disney",
    "watcha",
    "ott_summary",
    "previous_ott_summary",
    "lookup_status",
    "note",
    "snapshot_json",
    "previous_snapshot_json",
]

PROVIDER_ALIASES: dict[str, tuple[str, ...]] = {
    "넷플릭스": ("넷플릭스", "netflix"),
    "쿠팡플레이": ("쿠팡플레이", "coupang play", "coupangplay"),
    "티빙": ("티빙", "tving"),
    "웨이브": ("웨이브", "wavve"),
    "디즈니+": ("디즈니+", "디즈니 플러스", "disney+", "disney plus"),
    "왓챠": ("왓챠", "watcha"),
    "라프텔": ("라프텔", "laftel"),
    "Apple TV": ("apple tv", "애플tv", "애플 tv"),
    "아마존 프라임 비디오": ("아마존 프라임 비디오", "prime video", "amazon prime"),
    "씨네폭스": ("씨네폭스", "cinefox"),
}

# 외부 재생 링크의 도메인은 화면 문구보다 안정적인 제공처 근거다.
PROVIDER_DOMAINS: dict[str, tuple[str, ...]] = {
    "넷플릭스": ("netflix.com",),
    "쿠팡플레이": ("coupangplay.com", "coupang.com/play"),
    "티빙": ("tving.com",),
    "웨이브": ("wavve.com",),
    "디즈니+": ("disneyplus.com",),
    "왓챠": ("watcha.com", "watcha.co.kr"),
    "라프텔": ("laftel.net",),
    "Apple TV": ("tv.apple.com",),
    "아마존 프라임 비디오": ("primevideo.com", "amazon.com/gp/video"),
    "씨네폭스": ("cinefox.com",),
}


# -----------------------------------------------------------------------------
# Design
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
:root {
  --navy:#061858;
  --navy2:#0b2472;
  --text:#111a3b;
  --muted:#6d7488;
  --line:#e3e6ef;
  --bg:#f7f8fc;
  --green:#18a52b;
  --red:#ee2438;
}
.stApp { background:var(--bg); }
.block-container { max-width:1560px; padding:0 2rem 3rem; }
header[data-testid="stHeader"] { background:transparent; }
[data-testid="stToolbar"] { right:1rem; }

.topbar {
  margin-left:-2rem; margin-right:-2rem; padding:22px 34px;
  background:linear-gradient(110deg,var(--navy),#071e64 62%,#071a56);
  color:white; display:flex; align-items:center; justify-content:space-between;
  box-shadow:0 3px 16px rgba(7,24,88,.14);
}
.brand { display:flex; align-items:baseline; gap:22px; }
.brand-main { font-size:34px; line-height:1; font-weight:950; letter-spacing:-1.2px; }
.brand-sub { font-size:20px; font-weight:850; letter-spacing:-.5px; }
.update-pill {
  border:1px solid rgba(255,255,255,.20); background:rgba(255,255,255,.08);
  border-radius:8px; padding:10px 13px; font-size:12px; font-weight:800; color:#eff4ff;
}

.intro { padding:28px 4px 17px; }
.intro-title { font-size:24px; color:var(--text); font-weight:950; letter-spacing:-.7px; }
.intro-sub { margin-top:7px; font-size:14px; color:var(--muted); }

.control-title { font-size:13px; color:#171c33; font-weight:900; margin:0 0 7px; }
div[data-testid="stVerticalBlockBorderWrapper"] {
  background:white; border:1px solid var(--line) !important; border-radius:12px !important;
  box-shadow:0 2px 8px rgba(17,26,59,.025);
}
.stTextInput input, .stDateInput input { min-height:46px; }
div[data-baseweb="select"] > div { min-height:46px; }
.stButton > button, .stDownloadButton > button {
  min-height:46px; border-radius:8px; font-weight:900;
}
.stButton > button[kind="primary"] { background:#101f7b; border-color:#101f7b; }

.table-shell {
  margin-top:18px; background:white; border:1px solid var(--line); border-radius:12px;
  overflow:auto; box-shadow:0 2px 9px rgba(17,26,59,.025);
}
.comparison-table {
  width:100%; border-collapse:collapse; min-width:1380px; table-layout:fixed;
}
.comparison-table th {
  height:70px; background:#fbfbfd; color:#171b34; padding:12px 8px; font-size:12px;
  font-weight:950; border-right:1px solid var(--line); border-bottom:1px solid var(--line);
  text-align:center; vertical-align:middle; white-space:nowrap;
}
.comparison-table td {
  height:118px; color:#25304d; padding:9px 8px; font-size:13px;
  border-right:1px solid var(--line); border-bottom:1px solid var(--line);
  text-align:center; vertical-align:middle;
}
.comparison-table tr:last-child td { border-bottom:0; }
.comparison-table th:last-child, .comparison-table td:last-child { border-right:0; }
.comparison-table tbody tr:hover { background:#fafcff; }
.title-col { text-align:left !important; }
.title-wrap { display:flex; align-items:center; gap:14px; min-width:0; }
.title-copy { min-width:0; }
.provider-head {
  display:flex; align-items:center; justify-content:center; gap:4px;
  width:100%; min-height:30px; line-height:1.2;
}
.ott-cell { padding-left:4px !important; padding-right:4px !important; }
.poster {
  width:66px; height:94px; object-fit:cover; border-radius:7px; flex:0 0 auto;
  background:#e9ecf4; box-shadow:0 2px 6px rgba(20,28,60,.14);
}
.title-main { font-weight:950; font-size:14px; color:#121a35; line-height:1.4; }
.title-sub { font-size:11px; color:#747d93; margin-top:5px; line-height:1.55; }
.title-sub a { color:#193fb0; text-decoration:none; font-weight:800; }
.type-badge { display:inline-block; border-radius:6px; padding:5px 9px; font-size:11px; font-weight:900; }
.type-drama { color:#1764c0; background:#e9f3ff; }
.type-movie { color:#7346c3; background:#f1eaff; }
.type-variety { color:#c15d10; background:#fff0df; }
.type-ani { color:#087f6b; background:#e6f8f3; }
.type-kids { color:#ba397d; background:#ffebf5; }
.type-etc { color:#586174; background:#eef0f4; }
.ox-o { color:var(--green); font-size:22px; font-weight:950; }
.ox-x { color:var(--red); font-size:22px; font-weight:950; }
.provider-n { color:#df0017; font-size:20px; font-weight:950; margin-right:5px; }
.provider-c { color:#15a7ed; font-size:19px; font-weight:950; margin-right:5px; }
.provider-t { color:#e80048; font-size:19px; font-weight:950; margin-right:5px; }
.provider-w { color:#145cff; font-size:19px; font-weight:950; margin-right:5px; }
.provider-d { color:#1f72bd; font-size:15px; font-weight:950; margin-right:5px; }
.provider-wa { color:#e71357; font-size:19px; font-weight:950; margin-right:5px; }
.action-wrap { display:flex; justify-content:center; gap:6px; }
.icon-button {
  display:inline-flex; align-items:center; justify-content:center; width:34px; height:34px;
  border:1px solid #d7dce8; border-radius:7px; background:white; color:#303b59;
  font-size:16px; text-decoration:none; font-weight:900;
}
.icon-button:hover { border-color:#132b91; color:#132b91; background:#f4f7ff; }
.empty-box {
  margin-top:18px; padding:58px 20px; text-align:center; background:white;
  border:1px dashed #cbd1df; border-radius:12px; color:#737b91;
}
.guide-box {
  background:#eef3ff; border:1px solid #d9e4ff; border-radius:9px; color:#2d3f71;
  padding:13px 15px; font-size:13px; line-height:1.7; margin-bottom:12px;
}
.delete-box {
  background:#fff4f5; border:1px solid #ffd4d9; border-radius:10px;
  padding:13px 15px; color:#8c2735; font-weight:800;
}
.footer-note { color:#7c8498; font-size:11px; padding:14px 4px 0; }
.dialog-summary {
  background:#f6f8ff; border:1px solid #e0e6fb; border-radius:10px;
  padding:12px 14px; margin:4px 0 12px; color:#293555; font-size:13px; line-height:1.7;
}
.dialog-warning {
  background:#fff8e8; border:1px solid #f5dfa7; border-radius:10px;
  padding:11px 13px; color:#73540d; font-size:12px; line-height:1.65; margin:8px 0;
}
.history-status {
  display:inline-block; border-radius:999px; padding:4px 9px; font-size:11px; font-weight:900;
  background:#eef3ff; color:#24458f;
}

.native-head {
  min-height:52px; display:flex; align-items:center; justify-content:center;
  text-align:center; font-size:12px; font-weight:950; color:#171b34; line-height:1.25;
}
.native-head.left { justify-content:flex-start; text-align:left; }
.native-cell { width:100%; text-align:center; font-size:13px; color:#25304d; }
.native-ox { display:flex; align-items:center; justify-content:center; min-height:82px; }

/* v11: 카드가 여러 개로 보이지 않도록 하나의 표처럼 연결한다. */
.st-key-comparison_table_shell {
  background:white; border:1px solid var(--line); border-radius:12px;
  overflow:hidden; box-shadow:0 2px 9px rgba(17,26,59,.025); padding:0 !important;
}
.st-key-comparison_header {
  background:#fbfbfd; border-bottom:1px solid var(--line); padding:0 12px;
}
[class*="st-key-content_row_"] {
  background:white; border-bottom:1px solid var(--line); padding:8px 12px;
}
[class*="st-key-content_row_"]:hover { background:#fafcff; }
.st-key-comparison_table_shell [data-testid="stMarkdownContainer"] p { margin-bottom:0; }
[class*="st-key-native_refresh_"] button,
[class*="st-key-native_delete_"] button {
  width:36px !important; min-width:36px !important; height:36px !important;
  min-height:36px !important; padding:0 !important; border-radius:7px !important;
  background:white !important; border:1px solid #d7dce8 !important;
  color:#24407f !important; font-size:16px !important;
}
[class*="st-key-native_refresh_"] button:hover,
[class*="st-key-native_delete_"] button:hover {
  border-color:#132b91 !important; color:#132b91 !important; background:#f4f7ff !important;
}
.search-result-title {
  display:flex; align-items:center; gap:8px; font-size:13px; font-weight:950;
  color:#18213d; margin:4px 2px 9px;
}
.search-result-count {
  display:inline-flex; align-items:center; justify-content:center; min-width:26px; height:22px;
  padding:0 8px; border-radius:999px; background:#edf2ff; color:#20409a; font-size:11px; font-weight:900;
}
.search-result-note { color:#747d93; font-size:11px; font-weight:500; }
.pagination-info { text-align:center; color:#667087; font-size:12px; padding-top:12px; }

/* 검색 결과: 포스터 5개가 보이는 고정 높이 + 내부 스크롤 */
.st-key-candidate_results_shell {
  padding:0 12px !important; background:#fbfcff !important;
  border:1px solid #dfe4ef !important; border-radius:11px !important;
}
[class*="st-key-candidate_row_"] {
  min-height:92px; padding:8px 2px !important; border-bottom:1px solid #e7eaf2;
}
[class*="st-key-candidate_row_"]:last-child { border-bottom:0; }
[class*="st-key-candidate_row_"] [data-testid="stHorizontalBlock"] { align-items:center; }
[class*="st-key-candidate_row_"] [data-testid="stImage"] { margin:0 !important; }
[class*="st-key-candidate_row_"] [data-testid="stImage"] img {
  width:58px !important; height:80px !important; object-fit:cover !important;
  border-radius:7px !important; box-shadow:0 2px 7px rgba(16,29,74,.12);
}
.candidate-title { color:#111a3b; font-size:14px; font-weight:950; line-height:1.35; }
.candidate-meta { color:#7a8295; font-size:11px; margin-top:5px; }
[class*="st-key-add_candidate_"] button {
  min-height:38px !important; height:38px !important; padding:0 13px !important;
  border-radius:8px !important; font-size:12px !important; font-weight:850 !important;
  border-color:#d7ddea !important; background:white !important; color:#263653 !important;
}
[class*="st-key-add_candidate_"] button:hover {
  border-color:#173b9b !important; color:#173b9b !important; background:#f5f7ff !important;
}
.st-key-search_results_close button {
  min-height:38px !important; height:38px !important; margin-top:9px;
  border-radius:8px !important; color:#48526b !important;
}

/* 등록 콘텐츠 필터: 모든 입력·버튼·저장 상태의 높이와 기준선을 통일 */
.st-key-content_filter_toolbar {
  padding:11px 13px !important; background:white !important;
  border:1px solid var(--line) !important; border-radius:12px !important;
}
.st-key-content_filter_toolbar [data-testid="stHorizontalBlock"] { align-items:center; }
.st-key-content_filter_toolbar .stTextInput,
.st-key-content_filter_toolbar .stSelectbox,
.st-key-content_filter_toolbar .stButton { margin-bottom:0 !important; }
.st-key-content_filter_toolbar input,
.st-key-content_filter_toolbar div[data-baseweb="select"] > div,
.st-key-content_filter_toolbar button { min-height:44px !important; height:44px !important; }
.filter-tilde {
  height:44px; display:flex; align-items:center; justify-content:center;
  color:#6d7488; font-size:18px; font-weight:900;
}
.storage-pill {
  min-height:44px; display:flex; align-items:center; justify-content:center; gap:7px;
  border:1px solid #e1e5ef; border-radius:8px; background:#f8f9fc;
  color:#677086; font-size:11px; font-weight:800; white-space:nowrap;
}
.storage-dot { width:7px; height:7px; border-radius:50%; display:inline-block; background:#1aa34a; }
.storage-dot.temp { background:#e29b25; }
.st-key-reset_content_filters button {
  color:#3f4b67 !important; background:#f8f9fc !important; border-color:#dde2ed !important;
  font-size:12px !important;
}
.st-key-reset_content_filters button:hover {
  color:#173b9b !important; border-color:#aab9e2 !important; background:#f3f6ff !important;
}

/* 연결형 표의 여백과 세로 기준선 정돈 */
.st-key-comparison_header { padding-left:14px !important; padding-right:14px !important; }
[class*="st-key-content_row_"] { padding:7px 14px !important; }
[class*="st-key-content_row_"] [data-testid="stHorizontalBlock"] { align-items:center; }

/* v13: 기능과 배치는 유지하고 정렬·구분선·버튼 톤만 정돈 */
:root {
  --navy:#0b2a73;
  --navy2:#173f9f;
  --text:#101a38;
  --muted:#717b91;
  --line:#dce2ec;
  --bg:#f7f9fc;
}

/* 전체 카드와 입력창: 흰 배경 + 얇은 선 + 아주 약한 그림자 */
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-color:var(--line) !important;
  box-shadow:0 3px 12px rgba(16,35,83,.035) !important;
}
div[data-baseweb="input"],
div[data-baseweb="select"] > div {
  background:#fff !important;
  border-color:#d8deea !important;
}
.stTextInput input, .stDateInput input { color:#1d2947 !important; }

/* 버튼 톤: 1번 시안의 네이비 포인트 */
.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] button {
  border-radius:9px !important;
  box-shadow:none !important;
  transition:background .16s ease,border-color .16s ease,color .16s ease,transform .16s ease;
}
.stButton > button:hover,
.stDownloadButton > button:hover {
  border-color:#9eb0da !important;
  color:#113785 !important;
  background:#f7f9ff !important;
}
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button {
  background:linear-gradient(180deg,#173f9f 0%,#0b2a73 100%) !important;
  border-color:#0b2a73 !important;
  color:white !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button:hover {
  background:linear-gradient(180deg,#224db2 0%,#123587 100%) !important;
  border-color:#123587 !important;
  color:white !important;
}

/* 등록 표: 헤더·행·포스터·텍스트·버튼의 중심선을 동일하게 맞춘다. */
.st-key-comparison_table_shell {
  border-color:var(--line) !important;
  box-shadow:0 4px 14px rgba(16,35,83,.035) !important;
}
.st-key-comparison_table_shell > div[data-testid="stVerticalBlock"] {
  gap:0 !important;
}
.st-key-comparison_header {
  min-height:54px;
  padding:0 16px !important;
  background:#fbfcff !important;
  border-bottom:1px solid #d7deea !important;
}
.native-head {
  min-height:54px;
  line-height:1.25;
  display:flex;
  align-items:center;
  justify-content:center;
}
.native-head.left { justify-content:flex-start; }
[class*="st-key-content_row_"] {
  min-height:112px;
  padding:9px 16px !important;
  border-bottom:1px solid #dfe4ed !important;
  box-sizing:border-box;
}
[class*="st-key-content_row_"]:last-child { border-bottom:0 !important; }
[class*="st-key-content_row_"] [data-testid="stHorizontalBlock"] {
  align-items:center !important;
}
[class*="st-key-content_row_"] [data-testid="stColumn"] {
  align-self:center !important;
}
[class*="st-key-content_row_"] [data-testid="stMarkdownContainer"] {
  display:flex;
  flex-direction:column;
  justify-content:center;
}
.poster {
  width:62px;
  height:88px;
  border-radius:8px;
  box-shadow:0 3px 9px rgba(20,35,76,.13);
  display:block;
}
.title-main { font-size:14px; line-height:1.35; }
.title-sub { margin-top:6px; line-height:1.45; }
.native-cell {
  min-height:88px;
  display:flex;
  align-items:center;
  justify-content:center;
  line-height:1.35;
}
.native-ox { min-height:88px; }
[class*="st-key-native_refresh_"] button,
[class*="st-key-native_delete_"] button {
  width:36px !important;
  min-width:36px !important;
  height:36px !important;
  min-height:36px !important;
  margin:auto !important;
  border-radius:8px !important;
  border-color:#cfd7e6 !important;
  color:#1a428f !important;
}

/* 검색 결과: 5개 높이 유지 + 각 결과 사이 명확한 구분선 */
.search-result-title { margin:8px 2px 10px; }
.st-key-candidate_results_shell {
  padding:0 !important;
  background:#fff !important;
  border-color:#d8dfeb !important;
  box-shadow:0 3px 12px rgba(16,35,83,.03) !important;
}
.st-key-candidate_results_shell > div[data-testid="stVerticalBlock"] {
  gap:0 !important;
}
[class*="st-key-candidate_row_"] {
  min-height:94px;
  padding:10px 14px !important;
  border-bottom:1px solid #dce2ec !important;
  background:#fff;
  box-sizing:border-box;
}
[class*="st-key-candidate_row_"]:last-child { border-bottom:0 !important; }
[class*="st-key-candidate_row_"]:hover { background:#f9fbff !important; }
[class*="st-key-candidate_row_"] [data-testid="stHorizontalBlock"] {
  align-items:center !important;
}
[class*="st-key-candidate_row_"] [data-testid="stImage"] img {
  width:56px !important;
  height:78px !important;
  border-radius:8px !important;
}
.candidate-title { font-size:14px; line-height:1.35; }
.candidate-meta { margin-top:6px; }
[class*="st-key-add_candidate_"] button {
  height:40px !important;
  min-height:40px !important;
  border-radius:9px !important;
  border-color:#cfd7e6 !important;
  color:#193d85 !important;
}
.st-key-search_results_close button {
  min-height:40px !important;
  height:40px !important;
  border-radius:9px !important;
}

/* 필터바는 높이와 기준선만 맞추고 구조는 유지 */
.st-key-content_filter_toolbar {
  border-color:var(--line) !important;
  box-shadow:0 3px 12px rgba(16,35,83,.03) !important;
}
.st-key-content_filter_toolbar [data-testid="stHorizontalBlock"] {
  align-items:center !important;
}
.storage-pill {
  background:#fbfcff;
  border-color:#dce2ec;
  color:#58647d;
}


/* v14: 검색 결과와 등록 목록의 행 구분선을 실제 컨테이너 폭 전체에 표시 */
[class*="st-key-candidate_row_"],
[class*="st-key-content_row_"] {
  position:relative !important;
}
[class*="st-key-candidate_row_"]::after,
[class*="st-key-content_row_"]::after {
  content:"";
  position:absolute;
  left:14px;
  right:14px;
  bottom:0;
  height:1px;
  background:#cfd7e5;
  pointer-events:none;
}
[class*="st-key-candidate_row_"]:last-child::after,
[class*="st-key-content_row_"]:last-child::after { display:none; }

/* 저장 상태 배지를 필터 입력창과 정확히 같은 높이·기준선에 배치 */
.st-key-content_filter_toolbar [data-testid="stMarkdownContainer"] {
  min-height:44px;
  height:44px;
  display:flex;
  align-items:center;
  width:100%;
}
.storage-pill {
  width:100%;
  height:44px;
  min-height:44px;
  margin:0 !important;
  box-sizing:border-box;
  display:flex;
  align-items:center;
  justify-content:center;
  border:1px solid #d9e0eb;
  background:#fbfcff;
}
.storage-pill.temporary {
  background:#fffaf0;
  border-color:#ead8ad;
  color:#74591d;
}

/* 번호·선택 체크박스 */
.selection-head,
.row-number {
  min-height:54px;
  display:flex;
  align-items:center;
  justify-content:center;
  color:#6f7890;
  font-size:11px;
  font-weight:850;
  font-variant-numeric:tabular-nums;
}
.row-number { min-height:88px; font-size:12px; }
[class*="st-key-bulk_select_"] { display:flex; align-items:center; justify-content:center; }
[class*="st-key-bulk_select_"] [data-testid="stCheckbox"] { margin:0 auto !important; }
[class*="st-key-bulk_select_"] label { padding:0 !important; }

/* 선택 콘텐츠 일괄 작업 바 */
.st-key-bulk_action_bar {
  margin:12px 0 8px;
  padding:9px 12px !important;
  border:1px solid #d9e1ef !important;
  border-radius:10px !important;
  background:#f7f9ff !important;
  box-shadow:none !important;
}
.bulk-selected-text {
  min-height:40px;
  display:flex;
  align-items:center;
  color:#24365f;
  font-size:12px;
  font-weight:850;
}
.st-key-bulk_delete_button button {
  min-height:40px !important;
  height:40px !important;
  background:#fff5f6 !important;
  border-color:#edcbd0 !important;
  color:#b42d3d !important;
}
.st-key-bulk_delete_button button:hover {
  background:#fff0f2 !important;
  border-color:#dc8f99 !important;
  color:#9d1f30 !important;
}

/* 전체 최신화 버튼: 영구 저장 상태 옆에서 같은 높이로 정렬 */
.st-key-bulk_refresh_all button {
  min-height:44px !important;
  height:44px !important;
  border-radius:8px !important;
  border-color:#b9c7e6 !important;
  background:#f3f6ff !important;
  color:#173b87 !important;
  font-size:11px !important;
  font-weight:900 !important;
  white-space:nowrap !important;
}
.st-key-bulk_refresh_all button:hover {
  border-color:#7e96cf !important;
  background:#eaf0ff !important;
  color:#0d2f78 !important;
}
.st-key-bulk_refresh_all button:disabled {
  opacity:.5 !important;
}

/* 관리 버튼은 링크가 아니라 Streamlit 기본 버튼이라 URL 이동이 발생하지 않는다. */

@media (max-width:800px) {
  .block-container { padding-left:1rem; padding-right:1rem; }
  .topbar { margin-left:-1rem; margin-right:-1rem; padding:18px; }
  .brand { display:block; }
  .brand-main { font-size:26px; }
  .brand-sub { display:block; margin-top:7px; font-size:15px; }
  .update-pill { display:none; }
}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# General helpers
# -----------------------------------------------------------------------------
def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def deduplicate_candidates_for_display(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    """Collapse duplicate search cards while preserving genuinely different years/types."""
    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    order: list[tuple[str, str, str]] = []
    for candidate in candidates:
        title = clean_text(candidate.get("title", ""))
        year = clean_text(candidate.get("year", ""))
        content_type = clean_text(candidate.get("content_type", ""))
        key = (normalize_title(title), year, content_type)
        if not key[0]:
            continue
        if key not in unique:
            unique[key] = candidate
            order.append(key)
            continue
        # Prefer the duplicate carrying a concrete detail URL and poster.
        current = unique[key]
        current_score = int(bool(clean_text(current.get("url", "")))) + int(bool(clean_text(current.get("poster_url", ""))))
        new_score = int(bool(clean_text(candidate.get("url", "")))) + int(bool(clean_text(candidate.get("poster_url", ""))))
        if new_score > current_score:
            unique[key] = candidate
    return [unique[key] for key in order]


def clear_content_search_results() -> None:
    for key in ("content_search_candidates", "content_search_query", "content_search_meta"):
        st.session_state.pop(key, None)


def reset_content_filters() -> None:
    st.session_state["content_title_filter"] = ""
    st.session_state["content_type_filter"] = "전체"
    st.session_state["start_month_filter"] = "전체"
    st.session_state["end_month_filter"] = "전체"
    st.session_state["content_page"] = 1


def now_kst_text() -> str:
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y.%m.%d %H:%M")


def normalize_title(value: str) -> str:
    value = clean_text(value).lower()
    value = re.sub(r"\([^)]*\)|\[[^]]*\]", "", value)
    value = re.sub(r"시즌\s*\d+|season\s*\d+", "", value, flags=re.I)
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in {"1", "true", "t", "yes", "y", "o"}


def empty_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=DATA_COLUMNS)


def normalize_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_dataframe()
    result = df.copy().fillna("")
    for column in DATA_COLUMNS:
        if column not in result.columns:
            result[column] = ""
    result = result[DATA_COLUMNS]
    for column in OTT_COLUMNS.values():
        result[column] = result[column].apply(as_bool)
    result["title"] = result["title"].astype(str).str.strip()
    return result[result["title"] != ""].copy()


def empty_history_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=HISTORY_COLUMNS)


def normalize_history_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_history_dataframe()
    result = df.copy().fillna("")
    for column in HISTORY_COLUMNS:
        if column not in result.columns:
            result[column] = ""
    result = result[HISTORY_COLUMNS]
    for column in OTT_COLUMNS.values():
        result[column] = result[column].apply(as_bool)
    return result.copy()


def secret_value(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return clean_text(st.secrets[name])
        if "github" in st.secrets and name in st.secrets["github"]:
            return clean_text(st.secrets["github"][name])
    except Exception:
        pass
    return default


# -----------------------------------------------------------------------------
# Persistent data: GitHub API or local CSV
# -----------------------------------------------------------------------------
def github_config() -> dict[str, str] | None:
    token = secret_value("GITHUB_TOKEN")
    repo = secret_value("GITHUB_REPO", "cig7624-art/btv-max-ott-dashboard")
    if not token or not repo:
        return None
    return {
        "token": token,
        "repo": repo,
        "branch": secret_value("GITHUB_BRANCH", "main"),
        "path": secret_value("GITHUB_DATA_PATH", "btv_max_contents.csv"),
        "history_path": secret_value("GITHUB_HISTORY_PATH", "btv_max_history.csv"),
    }


def github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "btv-max-ott-dashboard",
    }


def read_github_csv_path(
    cfg: dict[str, str],
    path: str,
    normalizer: Any,
    empty_factory: Any,
) -> pd.DataFrame:
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{path}"
    response = requests.get(
        url,
        headers=github_headers(cfg["token"]),
        params={"ref": cfg["branch"]},
        timeout=20,
    )
    if response.status_code == 404:
        return empty_factory()
    response.raise_for_status()
    payload = response.json()
    raw = base64.b64decode(payload["content"]).decode("utf-8-sig")
    if not raw.strip():
        return empty_factory()
    return normalizer(pd.read_csv(io.StringIO(raw)))


def write_github_csv_path(
    cfg: dict[str, str],
    path: str,
    df: pd.DataFrame,
    message: str,
    normalizer: Any,
) -> None:
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{path}"
    headers = github_headers(cfg["token"])
    current = requests.get(
        url,
        headers=headers,
        params={"ref": cfg["branch"]},
        timeout=20,
    )
    sha = None
    if current.status_code == 200:
        sha = current.json().get("sha")
    elif current.status_code != 404:
        current.raise_for_status()

    export_df = normalizer(df)
    csv_text = export_df.to_csv(index=False, quoting=csv.QUOTE_MINIMAL)
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(csv_text.encode("utf-8-sig")).decode("ascii"),
        "branch": cfg["branch"],
    }
    if sha:
        body["sha"] = sha

    response = requests.put(url, headers=headers, json=body, timeout=30)
    response.raise_for_status()


def atomic_write_csv(path: Path, df: pd.DataFrame, normalizer: Any, prefix: str) -> None:
    export_df = normalizer(df)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".csv.tmp",
        prefix=prefix,
        dir=path.parent,
        delete=False,
        encoding="utf-8-sig",
        newline="",
    ) as temp:
        export_df.to_csv(temp, index=False)
        temp.flush()
        temp_path = Path(temp.name)
    temp_path.replace(path)


def read_local_csv_path(path: Path, normalizer: Any, empty_factory: Any) -> pd.DataFrame:
    if not path.exists():
        return empty_factory()
    try:
        return normalizer(pd.read_csv(path))
    except pd.errors.EmptyDataError:
        return empty_factory()


@st.cache_data(ttl=15, show_spinner=False)
def load_data() -> pd.DataFrame:
    cfg = github_config()
    if cfg:
        try:
            return read_github_csv_path(cfg, cfg["path"], normalize_dataframe, empty_dataframe)
        except Exception as exc:
            st.warning(f"GitHub 데이터를 불러오지 못해 앱 내 CSV를 표시합니다: {exc}")
    return read_local_csv_path(LOCAL_DATA_PATH, normalize_dataframe, empty_dataframe)


@st.cache_data(ttl=15, show_spinner=False)
def load_history() -> pd.DataFrame:
    cfg = github_config()
    if cfg:
        try:
            return read_github_csv_path(
                cfg,
                cfg["history_path"],
                normalize_history_dataframe,
                empty_history_dataframe,
            )
        except Exception as exc:
            st.warning(f"GitHub 저장 기록을 불러오지 못해 앱 내 기록을 표시합니다: {exc}")
    return read_local_csv_path(
        LOCAL_HISTORY_PATH,
        normalize_history_dataframe,
        empty_history_dataframe,
    )


def write_current_data(df: pd.DataFrame, message: str) -> None:
    cfg = github_config()
    if cfg:
        write_github_csv_path(cfg, cfg["path"], df, message, normalize_dataframe)
    else:
        atomic_write_csv(LOCAL_DATA_PATH, df, normalize_dataframe, "btv_max_")


def write_history_data(history_df: pd.DataFrame, message: str) -> None:
    cfg = github_config()
    if cfg:
        write_github_csv_path(
            cfg,
            cfg["history_path"],
            history_df,
            message,
            normalize_history_dataframe,
        )
    else:
        atomic_write_csv(
            LOCAL_HISTORY_PATH,
            history_df,
            normalize_history_dataframe,
            "btv_history_",
        )


def row_snapshot(row: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in DATA_COLUMNS:
        value = row.get(column, "") if hasattr(row, "get") else ""
        if column in OTT_COLUMNS.values():
            data[column] = as_bool(value)
        else:
            data[column] = clean_text(value)
    return data


def ott_summary(row: Any) -> str:
    names = [name for name, column in OTT_COLUMNS.items() if as_bool(row.get(column, False))]
    return ", ".join(names) if names else "없음"


def make_history_event(
    action: str,
    row: Any,
    previous_row: Any | None = None,
    note: str = "",
) -> dict[str, Any]:
    current = row_snapshot(row)
    previous = row_snapshot(previous_row) if previous_row is not None else {}
    event: dict[str, Any] = {
        "history_id": uuid.uuid4().hex[:16],
        "timestamp": now_kst_text(),
        "action": action,
        "row_id": current.get("id", "") or previous.get("id", ""),
        "title": current.get("title", "") or previous.get("title", ""),
        "btv_update_date": current.get("btv_update_date", "") or previous.get("btv_update_date", ""),
        "content_type": current.get("content_type", "") or previous.get("content_type", ""),
        "open_year": current.get("open_year", "") or previous.get("open_year", ""),
        "poster_url": current.get("poster_url", "") or previous.get("poster_url", ""),
        "source_url": current.get("source_url", "") or previous.get("source_url", ""),
        "ott_summary": ott_summary(current) if current else "없음",
        "previous_ott_summary": ott_summary(previous) if previous else "",
        "lookup_status": current.get("lookup_status", "") or previous.get("lookup_status", ""),
        "note": clean_text(note),
        "snapshot_json": json.dumps(current, ensure_ascii=False),
        "previous_snapshot_json": json.dumps(previous, ensure_ascii=False) if previous else "",
    }
    for column in OTT_COLUMNS.values():
        event[column] = as_bool(current.get(column, False)) if current else False
    return event


def append_history_events(events: list[dict[str, Any]], message: str) -> None:
    if not events:
        return
    history_df = load_history()
    updated_history = pd.concat([history_df, pd.DataFrame(events)], ignore_index=True)
    write_history_data(updated_history, message)
    load_history.clear()


def save_data(
    df: pd.DataFrame,
    message: str,
    history_events: list[dict[str, Any]] | None = None,
) -> str:
    """현재 목록을 먼저 저장하고, 변경 기록은 별도 누적 파일에 추가한다.

    반환값이 있으면 목록 저장은 성공했지만 기록 저장만 실패한 것이다.
    """
    write_current_data(df, message)
    history_warning = ""
    if history_events:
        try:
            append_history_events(history_events, f"History: {message}")
        except Exception as exc:
            history_warning = f"목록은 저장됐지만 변경 기록 저장은 실패했습니다: {exc}"
    load_data.clear()
    return history_warning


def build_backup_zip(df: pd.DataFrame, history_df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "btv_max_contents.csv",
            normalize_dataframe(df).to_csv(index=False).encode("utf-8-sig"),
        )
        archive.writestr(
            "btv_max_history.csv",
            normalize_history_dataframe(history_df).to_csv(index=False).encode("utf-8-sig"),
        )
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# Kinolights crawler
# -----------------------------------------------------------------------------
def browser_launch_kwargs() -> dict[str, Any]:
    for browser_path in (
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
    ):
        if Path(browser_path).exists():
            return {
                "headless": True,
                "executable_path": browser_path,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            }
    return {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    }


def extract_subscription_section(text: str) -> str:
    """본문에서 정액제/바로 보기 영역을 넓게 잘라낸다.

    키노라이츠는 작품마다 '정액제', '스트리밍', '바로 보기' 등 표기가
    달라질 수 있어 한 가지 시작 문구에만 의존하지 않는다.
    """
    decoded = html.unescape(clean_text(text))
    start_markers = ["정액제", "바로 보기", "바로보기", "스트리밍", "구독"]
    end_markers = [
        "대여",
        "구매",
        "작품 정보",
        "에피소드",
        "비슷한 작품",
        "코멘트",
        "리뷰",
        "출연",
        "감독",
    ]
    starts = [decoded.find(marker) for marker in start_markers if decoded.find(marker) >= 0]
    if not starts:
        return ""
    section = decoded[min(starts) :]
    cuts = [section.find(marker) for marker in end_markers if section.find(marker) > 0]
    if cuts:
        section = section[: min(cuts)]
    return section[:8000]


def detect_providers(text: str) -> list[str]:
    lowered = html.unescape(clean_text(text)).lower()
    found: list[str] = []
    for canonical, aliases in PROVIDER_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            found.append(canonical)
    return found


def detect_direct_view_providers(text: str) -> list[str]:
    """전체 본문에서는 제공처 이름만 보지 않고 '바로 보기/시청' 근접 문구만 인정한다."""
    normalized = re.sub(r"\s+", " ", html.unescape(clean_text(text))).lower()
    action = r"(?:바로\s*보기|바로보기|시청하기|시청|정액제|스트리밍|구독)"
    found: list[str] = []
    for canonical, aliases in PROVIDER_ALIASES.items():
        matched = False
        for alias in aliases:
            alias_pattern = re.escape(alias.lower()).replace(r"\ ", r"\s*")
            if re.search(rf"{alias_pattern}.{{0,55}}{action}|{action}.{{0,55}}{alias_pattern}", normalized):
                matched = True
                break
        if matched:
            found.append(canonical)
    return found


def detect_provider_domains(text: str) -> list[str]:
    lowered = html.unescape(clean_text(text)).lower()
    return [
        canonical
        for canonical, domains in PROVIDER_DOMAINS.items()
        if any(domain.lower() in lowered for domain in domains)
    ]


def collect_provider_dom_evidence(page: Any) -> str:
    """재생 영역의 텍스트·로고 alt·외부 링크를 함께 수집한다.

    제공처가 화면 본문 텍스트가 아니라 이미지 alt, aria-label 또는 외부 링크
    도메인으로만 표시되는 경우가 있어 DOM 근거를 별도로 읽는다.
    """
    try:
        evidence = page.evaluate(
            r"""
            () => {
              const clean = v => (v || '').replace(/\s+/g, ' ').trim();
              const actionRe = /(정액제|바로\s*보기|바로보기|스트리밍|구독|시청)/i;
              const rows = [];
              const add = value => {
                const text = clean(value);
                if (text && !rows.includes(text)) rows.push(text);
              };
              const describe = el => {
                const parts = [
                  el.innerText,
                  el.textContent,
                  el.getAttribute?.('aria-label'),
                  el.getAttribute?.('title'),
                  el.getAttribute?.('alt'),
                  el.getAttribute?.('href'),
                  el.getAttribute?.('src'),
                ];
                for (const img of Array.from(el.querySelectorAll?.('img') || [])) {
                  parts.push(img.getAttribute('alt'), img.getAttribute('title'), img.getAttribute('src'));
                }
                for (const a of Array.from(el.querySelectorAll?.('a[href]') || [])) {
                  parts.push(a.href, a.innerText, a.getAttribute('aria-label'), a.getAttribute('title'));
                }
                return clean(parts.filter(Boolean).join(' | '));
              };

              // 외부 재생 링크는 자체가 가장 강한 근거다.
              for (const a of Array.from(document.querySelectorAll('a[href]'))) {
                const href = a.href || '';
                if (/netflix\.com|tving\.com|coupangplay\.com|coupang\.com\/play|wavve\.com|disneyplus\.com|watcha\.(com|co\.kr)|laftel\.net|tv\.apple\.com|primevideo\.com|cinefox\.com/i.test(href)) {
                  add(describe(a));
                }
              }

              // '바로 보기/정액제' 문구가 있는 작은 컨테이너만 수집한다.
              for (const el of Array.from(document.querySelectorAll('body *'))) {
                const own = clean(el.innerText || el.textContent || '');
                if (!own || !actionRe.test(own)) continue;
                let current = el;
                for (let depth = 0; current && depth < 5; depth += 1, current = current.parentElement) {
                  const text = clean(current.innerText || current.textContent || '');
                  if (text.length > 0 && text.length <= 2200) {
                    add(describe(current));
                    break;
                  }
                }
              }

              // 버튼/링크/이미지 자체에 제공처명이 붙은 경우.
              for (const el of Array.from(document.querySelectorAll('a, button, [role="button"], img[alt], [aria-label], [title]'))) {
                const desc = describe(el);
                if (actionRe.test(desc)) add(desc);
              }
              return rows.slice(0, 120).join('\n');
            }
            """
        )
        return clean_text(evidence)
    except Exception:
        return ""


def extract_detail_providers(page: Any, body_text: str) -> list[str]:
    """키노라이츠의 정액제 탭 제공처만 보수적으로 반환한다.

    핵심 안전장치:
    1) 탭에 표시된 정액제 건수를 먼저 읽는다.
    2) 정액제 건수가 0이면 다른 탭을 읽지 않고 즉시 빈 목록을 반환한다.
    3) 건수가 1개 이상이면 정액제 탭의 실제 클릭 가능한 부모를 눌러 전환한다.
    4) 화면에서 읽은 제공처 수가 탭 건수와 일치할 때만 결과를 인정한다.

    따라서 정액제가 0건인데 현재 선택된 대여/구매 탭의 제공처가 보이는 경우에도
    해당 제공처를 O로 오인하지 않는다.
    """
    try:
        # 제공처 탭이 지연 렌더링될 수 있어 페이지 중하단까지 이동한다.
        for ratio in (0.35, 0.62, 0.82):
            page.evaluate(
                "ratio => window.scrollTo(0, Math.max(0, document.body.scrollHeight * ratio))",
                ratio,
            )
            page.wait_for_timeout(300)
    except Exception:
        pass

    try:
        tab_info = page.evaluate(
            r"""
            () => {
              const clean = value => (value || '').replace(/\s+/g, ' ').trim();
              const visible = el => {
                if (!el) return false;
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                       Number(style.opacity || 1) !== 0 && rect.width > 0 && rect.height > 0;
              };
              const ownText = el => clean(el.innerText || el.textContent || '');
              const all = Array.from(document.querySelectorAll('body *')).filter(visible);
              const labels = all.filter(el => /^정액제(?:\s*\d+)?$/.test(ownText(el)));
              if (!labels.length) return {found:false, count:null, labelText:'', clicked:false};

              labels.sort((a, b) => {
                const at = ownText(a), bt = ownText(b);
                const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
                if (at.length !== bt.length) return at.length - bt.length;
                return (ar.width * ar.height) - (br.width * br.height);
              });
              const label = labels[0];
              const labelText = ownText(label);
              let match = labelText.match(/^정액제(?:\s*(\d+))?$/);
              let count = match && match[1] ? Number(match[1]) : null;

              // 숫자 배지가 별도 자식/형제 요소인 경우 가까운 탭 행 전체 텍스트에서 보완한다.
              let tabRow = label;
              for (let depth = 0; tabRow && depth < 7; depth += 1, tabRow = tabRow.parentElement) {
                const text = ownText(tabRow);
                if (text.length <= 260 && /정액제/.test(text) && /무료/.test(text) && /대여/.test(text) && /구매/.test(text)) {
                  const countMatch = text.match(/정액제\s*(\d+)/);
                  if (count === null && countMatch) count = Number(countMatch[1]);
                  break;
                }
              }

              // 키노라이츠 UI는 제공처가 0개인 탭에는 숫자를 표시하지 않는다.
              // 같은 탭 행에 대여/구매 숫자는 있는데 정액제 숫자가 없으면 0건으로 확정한다.
              if (count === null && tabRow) {
                const rowText = ownText(tabRow);
                if (/대여\s*\d+|구매\s*\d+|무료\s*\d+/.test(rowText)) count = 0;
              }

              let clickable = label;
              for (let depth = 0; clickable && depth < 7; depth += 1, clickable = clickable.parentElement) {
                const role = clickable.getAttribute?.('role') || '';
                const style = getComputedStyle(clickable);
                if (clickable.matches?.('button, a, [role="tab"], [role="button"], input') ||
                    role === 'tab' || role === 'button' || style.cursor === 'pointer') {
                  break;
                }
              }
              if (!clickable) clickable = label;
              clickable.scrollIntoView({block:'center'});

              // pointer/mouse 이벤트까지 보내 React/Vue 탭 핸들러가 확실히 실행되게 한다.
              for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
                try {
                  const EventCtor = type.startsWith('pointer') ? PointerEvent : MouseEvent;
                  clickable.dispatchEvent(new EventCtor(type, {bubbles:true, cancelable:true, view:window}));
                } catch (_) {}
              }
              try { clickable.click(); } catch (_) {}

              return {
                found:true,
                count,
                labelText,
                clicked:true,
                y:(tabRow || label).getBoundingClientRect().bottom + window.scrollY
              };
            }
            """
        )
    except Exception:
        return []

    if not isinstance(tab_info, dict) or not tab_info.get("found"):
        return []

    expected_count = tab_info.get("count")
    try:
        expected_count = int(expected_count) if expected_count is not None else None
    except Exception:
        expected_count = None

    # 정액제 0건은 가장 확실한 정보다. 현재 열려 있는 대여/구매 패널은 읽지 않는다.
    if expected_count == 0:
        return []

    try:
        page.wait_for_timeout(1100)
    except Exception:
        pass

    try:
        result = page.evaluate(
            r"""
            (expectedCount) => {
              const clean = value => (value || '').replace(/\s+/g, ' ').trim();
              const visible = el => {
                if (!el) return false;
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                       Number(style.opacity || 1) !== 0 && rect.width > 0 && rect.height > 0;
              };
              const textOf = el => clean(el.innerText || el.textContent || '');
              const all = Array.from(document.querySelectorAll('body *')).filter(visible);
              const labels = all.filter(el => /^정액제(?:\s*\d+)?$/.test(textOf(el)));
              if (!labels.length) return {providers:[], active:false};
              labels.sort((a,b) => {
                const ar=a.getBoundingClientRect(), br=b.getBoundingClientRect();
                return (ar.width*ar.height)-(br.width*br.height);
              });
              const label = labels[0];

              let interactive = label;
              for (let depth=0; interactive && depth<7; depth+=1, interactive=interactive.parentElement) {
                if (interactive.matches?.('button,a,[role="tab"],[role="button"]')) break;
              }
              if (!interactive) interactive = label;
              const attrText = clean([
                interactive.getAttribute?.('aria-selected'),
                interactive.getAttribute?.('aria-current'),
                interactive.getAttribute?.('data-state'),
                interactive.className,
              ].filter(Boolean).join(' ')).toLowerCase();
              let active = /(^|\s)(true|active|selected|current|on)(\s|$)/.test(attrText);

              let tabRow = label;
              for (let depth=0; tabRow && depth<7; depth+=1, tabRow=tabRow.parentElement) {
                const text=textOf(tabRow);
                if (text.length<=260 && /정액제/.test(text) && /무료/.test(text) && /대여/.test(text) && /구매/.test(text)) break;
              }
              const startY = (tabRow || label).getBoundingClientRect().bottom + window.scrollY + 4;
              const media = all.filter(el => /^미디어$/.test(textOf(el)))
                .map(el => el.getBoundingClientRect().top + window.scrollY)
                .filter(y => y > startY);
              const endY = media.length ? Math.min(...media) : startY + 1100;

              const defs = [
                ['넷플릭스', [/넷플릭스/i,/netflix/i], [/netflix\.com/i]],
                ['쿠팡플레이', [/쿠팡\s*플레이/i,/coupang\s*play/i], [/coupangplay\.com/i,/coupang\.com\/play/i]],
                ['티빙', [/티빙/i,/tving/i], [/tving\.com/i]],
                ['웨이브', [/웨이브/i,/wavve/i], [/wavve\.com/i]],
                ['디즈니+', [/디즈니\s*\+?/i,/disney\s*\+?/i], [/disneyplus\.com/i]],
                ['왓챠', [/왓챠/i,/watcha/i], [/watcha\.(com|co\.kr)/i]],
                ['라프텔', [/라프텔/i,/laftel/i], [/laftel\.net/i]],
                ['Apple TV', [/apple\s*tv/i,/애플\s*tv/i], [/tv\.apple\.com/i]],
                ['아마존 프라임 비디오', [/아마존\s*프라임/i,/prime\s*video/i], [/primevideo\.com/i]],
                ['씨네폭스', [/씨네폭스/i,/cinefox/i], [/cinefox\.com/i]],
              ];
              const found=[];
              const candidates=Array.from(document.querySelectorAll(
                'a,button,li,[role="button"],img[alt],[aria-label],[title]'
              )).filter(visible);
              for (const node of candidates) {
                const rect=node.getBoundingClientRect();
                const y=rect.top+window.scrollY+rect.height/2;
                if (y<=startY || y>=endY) continue;
                const text=clean([
                  node.innerText,node.textContent,node.getAttribute?.('alt'),
                  node.getAttribute?.('aria-label'),node.getAttribute?.('title')
                ].filter(Boolean).join(' | '));
                const href=clean(node.getAttribute?.('href') || '');
                if (text.length>140) continue;
                for (const [name,textPatterns,urlPatterns] of defs) {
                  if (found.includes(name)) continue;
                  if (textPatterns.some(re=>re.test(text)) || urlPatterns.some(re=>re.test(href))) found.push(name);
                }
              }

              // 활성 속성이 없는 UI도 있다. 이 경우 탭 건수와 읽은 제공처 수가 정확히 같을 때만
              // 탭 전환 성공으로 인정한다. 대여 패널을 잘못 읽으면 보통 건수가 달라져 차단된다.
              if (!active && Number.isInteger(expectedCount) && expectedCount > 0 && found.length === expectedCount) {
                active = true;
              }
              return {providers:found, active};
            }
            """,
            expected_count,
        )
    except Exception:
        return []

    if not isinstance(result, dict) or not result.get("active"):
        return []
    providers = [clean_text(x) for x in (result.get("providers") or []) if clean_text(x)]

    # 탭 숫자와 추출 결과가 다르면 다른 탭/추천 영역일 가능성이 있으므로 실패 폐쇄한다.
    if expected_count is not None and expected_count >= 0 and len(providers) != expected_count:
        return []
    return providers

def clean_candidate_title(raw_text: str, fallback: str = "") -> str:
    lines = [line.strip() for line in clean_text(raw_text).splitlines() if line.strip()]
    excluded = {"찜하기", "급상승", "신작", "공개예정작", "종료예정작"}
    for line in lines:
        if line in excluded or line.endswith("%") or re.fullmatch(r"\d{4}·.*", line):
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", line):
            continue
        return line
    return clean_text(fallback)


def candidate_title_from_link(link: Any, query: str) -> str:
    """Read the title attached to a result card without guessing from the query."""
    try:
        raw_text = clean_text(link.inner_text(timeout=1800))
        title = clean_candidate_title(raw_text)
        if title:
            return title
    except Exception:
        pass

    try:
        images = link.locator("img")
        for index in range(min(images.count(), 3)):
            image = images.nth(index)
            for attribute in ("alt", "title", "aria-label"):
                value = clean_candidate_title(clean_text(image.get_attribute(attribute)))
                if value:
                    return value
    except Exception:
        pass

    for attribute in ("aria-label", "title"):
        try:
            value = clean_candidate_title(clean_text(link.get_attribute(attribute)))
            if value:
                return value
        except Exception:
            pass

    # Some cards put the title on the immediate wrapper rather than the anchor.
    try:
        wrapper_text = clean_text(link.locator("xpath=..").inner_text(timeout=1800))
        title = clean_candidate_title(wrapper_text)
        if title and candidate_score(query, title, "") >= 45:
            return title
    except Exception:
        pass

    return ""

def candidate_score(query: str, candidate: str, requested_year: str, body_year: str = "") -> float:
    normalized_query = normalize_title(query)
    normalized_candidate = normalize_title(candidate)
    if not normalized_query or not normalized_candidate:
        return 0.0
    if normalized_query == normalized_candidate:
        score = 100.0
    elif normalized_query in normalized_candidate or normalized_candidate in normalized_query:
        score = 88.0
    else:
        score = SequenceMatcher(None, normalized_query, normalized_candidate).ratio() * 80
    if requested_year and body_year and requested_year == body_year:
        score += 10
    return score


def extract_year(text: str) -> str:
    match = re.search(r"(?<!\d)(19|20)\d{2}(?!\d)", clean_text(text))
    return match.group(0) if match else ""


def infer_content_type(text: str, source_url: str = "") -> str:
    """키노라이츠 카드/상세 문구에서 콘텐츠 구분을 자동 추정한다."""
    normalized = clean_text(text).lower()
    url = clean_text(source_url).lower()
    if any(keyword in normalized for keyword in ("키즈", "유아")):
        return "키즈"
    if any(keyword in normalized for keyword in ("애니메이션", "애니", "animation")):
        return "애니"
    if any(keyword in normalized for keyword in ("예능", "버라이어티", "리얼리티", "entertainment")):
        return "예능"
    if any(keyword in normalized for keyword in ("영화", "movie")) or "/movie/" in url:
        return "영화"
    if any(keyword in normalized for keyword in ("드라마", "시리즈", "tv드라마", "series")):
        return "드라마"
    if "/season/" in url:
        return "드라마"
    return "기타"


def normalize_image_url(src: str, base_url: str) -> str:
    src = clean_text(src)
    if not src or src.startswith("data:"):
        return ""
    if src.startswith("//"):
        return "https:" + src
    return urljoin(base_url, src)


def image_from_locator(locator: Any, base_url: str) -> str:
    for attribute in ("src", "data-src", "data-original"):
        try:
            value = locator.get_attribute(attribute)
            normalized = normalize_image_url(value, base_url)
            if normalized:
                return normalized
        except Exception:
            pass
    try:
        srcset = clean_text(locator.get_attribute("srcset"))
        if srcset:
            first = srcset.split(",")[0].strip().split(" ")[0]
            return normalize_image_url(first, base_url)
    except Exception:
        pass
    return ""


def visible_search_input(page: Any) -> Any | None:
    for selector in (
        "input[type='search']",
        "input[placeholder*='검색']",
        "input[aria-label*='검색']",
        "input",
    ):
        try:
            items = page.locator(selector)
            for index in range(min(items.count(), 10)):
                item = items.nth(index)
                if item.is_visible() and item.is_enabled():
                    return item
        except Exception:
            continue
    return None


def perform_kinolights_search(page: Any, query: str) -> None:
    """Enter a query and fire the events used by the mobile search UI."""
    page.goto("https://m.kinolights.com/search", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1200)

    search_input = visible_search_input(page)
    if search_input is None:
        raise RuntimeError("키노라이츠 검색창을 찾지 못했습니다.")

    search_input.click(timeout=5000)
    search_input.fill("")
    # React/Vue controlled inputs sometimes ignore fill() alone. Set the value
    # through the native setter and dispatch input/change/composition events.
    search_input.evaluate(
        r"""
        (el, value) => {
          const proto = Object.getPrototypeOf(el);
          const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
          if (descriptor && descriptor.set) descriptor.set.call(el, value);
          else el.value = value;
          el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:value}));
          el.dispatchEvent(new CompositionEvent('compositionend', {bubbles:true, data:value}));
          el.dispatchEvent(new Event('change', {bubbles:true}));
        }
        """,
        query,
    )
    search_input.press("Enter")
    page.wait_for_timeout(1800)

    # Wait until at least one image title is related to the entered query.
    # If the search UI did not react, the page still shows today's popular works;
    # those must never be mistaken for search results.
    normalized_query = normalize_title(query)
    for _ in range(12):
        try:
            alts = page.locator("img[alt]").evaluate_all(
                "els => els.map(el => (el.getAttribute('alt') || '').trim()).filter(Boolean)"
            )
            if any(
                normalized_query in normalize_title(alt)
                or normalize_title(alt) in normalized_query
                for alt in alts
                if normalize_title(alt)
            ):
                break
        except Exception:
            pass
        page.wait_for_timeout(500)


def collect_candidates_from_current_page(page: Any, query: str) -> list[dict[str, str]]:
    """Read each result from its own image node.

    The old implementation mixed text from a broad anchor/container with the
    first image in that container, which is why every title received the poster
    for '결혼의 완성'. Here the title and poster are always taken from the same
    img element. A detail URL is kept only when it is found in that image's own
    clickable ancestors.
    """
    raw_candidates = page.evaluate(
        r"""
        () => {
          const detailPattern = /\/(season|title|movie|content|contents)\//i;
          const clean = value => (value || '').replace(/\s+/g, ' ').trim();
          const absolute = value => {
            try { return new URL(value, location.href).href; }
            catch (_) { return value || ''; }
          };
          const imageSrc = img => {
            const srcset = img.getAttribute('srcset') || '';
            const srcsetFirst = srcset.split(',')[0]?.trim().split(/\s+/)[0] || '';
            return absolute(
              img.currentSrc || img.getAttribute('src') ||
              img.getAttribute('data-src') || img.getAttribute('data-original') ||
              srcsetFirst
            );
          };
          const ownDetailHref = img => {
            let current = img;
            for (let depth = 0; current && depth < 7; depth += 1, current = current.parentElement) {
              if (current.matches?.('a[href]') && detailPattern.test(current.href || '')) {
                return current.href;
              }
              // Only inspect links inside a compact card whose text includes
              // this image's alt title. Never scan a large shared container.
              const text = clean(current.innerText || '');
              const alt = clean(img.getAttribute('alt'));
              if (text.length > 0 && text.length < 350 && (!alt || text.includes(alt))) {
                const links = Array.from(current.querySelectorAll?.('a[href]') || [])
                  .filter(a => detailPattern.test(a.href || ''));
                if (links.length === 1) return links[0].href;
              }
            }
            return '';
          };
          const cardText = img => {
            let current = img;
            let best = '';
            for (let depth = 0; current && depth < 6; depth += 1, current = current.parentElement) {
              const text = clean(current.innerText || '');
              if (text && text.length < 350) best = text;
              if (current.matches?.('li, article, [role="listitem"]')) break;
            }
            return best;
          };

          const rows = [];
          const seen = new Set();
          for (const img of Array.from(document.querySelectorAll('img[alt]'))) {
            const title = clean(img.getAttribute('alt'));
            const poster = imageSrc(img);
            if (!title || !poster) continue;
            const text = cardText(img);
            const year = text.match(/(?:19|20)\d{2}/)?.[0] || '';
            const url = ownDetailHref(img);
            const key = `${title}|${poster}`;
            if (seen.has(key)) continue;
            seen.add(key);
            rows.push({title, poster_url:poster, url, year, card_text:text});
          }
          return rows;
        }
        """
    )

    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_candidates or []:
        candidate_title = clean_text(item.get("title", ""))
        normalized_query = normalize_title(query)
        normalized_candidate = normalize_title(candidate_title)
        is_related = (
            normalized_query in normalized_candidate
            or normalized_candidate in normalized_query
            or SequenceMatcher(None, normalized_query, normalized_candidate).ratio() >= 0.72
        )
        if not is_related:
            continue
        poster_url = normalize_image_url(clean_text(item.get("poster_url", "")), "https://m.kinolights.com/search")
        if not poster_url:
            continue
        key = f"{normalize_title(candidate_title)}|{poster_url}"
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "title": candidate_title,
                "poster_url": poster_url,
                "url": clean_text(item.get("url", "")),
                "year": clean_text(item.get("year", "")),
                "content_type": infer_content_type(
                    clean_text(item.get("card_text", "")),
                    clean_text(item.get("url", "")),
                ),
                "query": query,
            }
        )

    return sorted(
        candidates,
        key=lambda item: candidate_score(query, item["title"], "", item.get("year", "")),
        reverse=True,
    )[:20]


@st.cache_data(ttl=900, show_spinner=False)
def search_kinolights_candidates(query: str) -> list[dict[str, str]]:
    query = clean_text(query)
    if not query:
        return []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**browser_launch_kwargs())
            context = browser.new_context(
                viewport={"width": 430, "height": 1600},
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
            )
            page = context.new_page()
            page.set_default_timeout(12000)
            perform_kinolights_search(page, query)
            candidates = collect_candidates_from_current_page(page, query)
            context.close()
            browser.close()
            return candidates
    except Exception:
        return []


def detail_title_matches(page: Any, expected_title: str) -> bool:
    expected = normalize_title(expected_title)
    if not expected:
        return False
    texts: list[str] = []
    for selector, attribute in (
        ("meta[property='og:title']", "content"),
        ("meta[name='twitter:title']", "content"),
        ("h1", None),
        ("h2", None),
    ):
        try:
            locator = page.locator(selector).first
            value = locator.get_attribute(attribute) if attribute else locator.inner_text(timeout=1200)
            if value:
                texts.append(clean_text(value))
        except Exception:
            pass
    try:
        texts.append(clean_text(page.title()))
    except Exception:
        pass
    normalized_text = normalize_title(" ".join(texts))
    return expected in normalized_text or normalized_text in expected


def click_exact_candidate(page: Any, candidate: dict[str, str]) -> bool:
    expected_title = clean_text(candidate.get("title", ""))
    expected_poster = clean_text(candidate.get("poster_url", ""))
    images = page.locator("img[alt]")
    chosen = None
    for index in range(min(images.count(), 100)):
        image = images.nth(index)
        alt = clean_text(image.get_attribute("alt"))
        if normalize_title(alt) != normalize_title(expected_title):
            continue
        image_url = image_from_locator(image, page.url)
        if expected_poster and image_url and image_url != expected_poster:
            continue
        chosen = image
        break
    if chosen is None:
        return False

    before = page.url
    try:
        chosen.scroll_into_view_if_needed()
        chosen.click(force=True, timeout=5000)
        page.wait_for_timeout(1800)
    except Exception:
        pass
    if page.url != before and "/search" not in page.url:
        return True

    # Click only the nearest actual clickable ancestor of the exact image.
    try:
        clicked = chosen.evaluate(
            r"""
            img => {
              let current = img;
              for (let depth = 0; current && depth < 7; depth += 1, current = current.parentElement) {
                if (current.matches?.('a[href], button, [role="link"], [onclick]')) {
                  current.click();
                  return true;
                }
              }
              return false;
            }
            """
        )
        if clicked:
            page.wait_for_timeout(1800)
    except Exception:
        pass
    return page.url != before and "/search" not in page.url


def inspect_selected_candidate(context: Any, candidate: dict[str, str]) -> dict[str, Any]:
    detail = context.new_page()
    try:
        source_url = clean_text(candidate.get("url", ""))
        opened = False
        if source_url and re.search(r"/(season|title|movie|content|contents)/", source_url, re.I):
            detail.goto(source_url, wait_until="domcontentloaded", timeout=30000)
            detail.wait_for_timeout(1600)
            opened = detail_title_matches(detail, clean_text(candidate.get("title", "")))

        if not opened:
            perform_kinolights_search(detail, clean_text(candidate.get("query", candidate.get("title", ""))))
            if not click_exact_candidate(detail, candidate):
                return {
                    **candidate,
                    "providers": [],
                    "status": "상세 페이지 이동 실패",
                    "source_url": "",
                }
            detail.wait_for_timeout(1200)
            if not detail_title_matches(detail, clean_text(candidate.get("title", ""))):
                return {
                    **candidate,
                    "providers": [],
                    "status": "상세 작품 검증 실패",
                    "source_url": "",
                }

        body_text = clean_text(detail.locator("body").inner_text(timeout=8000))
        providers = extract_detail_providers(detail, body_text)
        return {
            **candidate,
            "providers": providers,
            "year": extract_year(body_text) or clean_text(candidate.get("year", "")),
            "content_type": infer_content_type(body_text[:3500], detail.url)
            or clean_text(candidate.get("content_type", ""))
            or "기타",
            # Keep the selected result image. Never replace it with a generic OG image.
            "poster_url": clean_text(candidate.get("poster_url", "")),
            "source_url": detail.url,
            "status": ("조회 완료: " + ", ".join(providers)) if providers else "주요 OTT 제공처 없음",
        }
    finally:
        detail.close()


@st.cache_data(ttl=1800, show_spinner=False)
def lookup_selected_kinolights(candidate_json: str) -> dict[str, Any]:
    import json

    try:
        candidate = json.loads(candidate_json)
    except Exception:
        return {"ok": False, "status": "선택 정보 오류", "providers": []}

    title = clean_text(candidate.get("title", ""))
    if not title or not clean_text(candidate.get("poster_url", "")):
        return {"ok": False, "status": "선택 콘텐츠 정보 부족", "providers": []}

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**browser_launch_kwargs())
            context = browser.new_context(
                viewport={"width": 430, "height": 1600},
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
            )
            result = inspect_selected_candidate(context, candidate)
            context.close()
            browser.close()
            status = clean_text(result.get("status", "조회 완료"))
            hard_failure = status in {"상세 페이지 이동 실패", "상세 작품 검증 실패"}
            return {
                "ok": not hard_failure,
                "status": status,
                "providers": result.get("providers", []) or [],
                "matched_title": title,
                "matched_year": clean_text(result.get("year", "")),
                "content_type": clean_text(result.get("content_type", ""))
                or clean_text(candidate.get("content_type", ""))
                or "기타",
                "source_url": clean_text(result.get("source_url", "")),
                "poster_url": clean_text(candidate.get("poster_url", "")),
            }
    except PlaywrightTimeoutError:
        return {
            "ok": False,
            "status": "OTT 조회 시간 초과",
            "providers": [],
            "matched_title": title,
            "matched_year": clean_text(candidate.get("year", "")),
            "source_url": clean_text(candidate.get("url", "")),
            "poster_url": clean_text(candidate.get("poster_url", "")),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": f"OTT 조회 오류: {str(exc)[:80]}",
            "providers": [],
            "matched_title": title,
            "matched_year": clean_text(candidate.get("year", "")),
            "source_url": clean_text(candidate.get("url", "")),
            "poster_url": clean_text(candidate.get("poster_url", "")),
        }


@st.cache_data(ttl=1800, show_spinner=False)
def lookup_kinolights(title: str, open_year: str = "") -> dict[str, Any]:
    """Exact-title refresh only. Partial queries must be selected in the UI."""
    candidates = search_kinolights_candidates(title)
    exact = [item for item in candidates if normalize_title(item.get("title", "")) == normalize_title(title)]
    if not exact:
        return {"ok": False, "status": "정확히 일치하는 작품을 다시 선택해 주세요", "providers": []}
    if open_year:
        year_matches = [item for item in exact if clean_text(item.get("year", "")) == clean_text(open_year)]
        if year_matches:
            exact = year_matches
    import json
    return lookup_selected_kinolights(json.dumps(exact[0], ensure_ascii=False))


def result_to_row(
    title: str,
    update_date: date,
    content_type: str,
    open_year: str,
    result: dict[str, Any],
    row_id: str | None = None,
    existing_poster_url: str = "",
) -> dict[str, Any]:
    providers = result.get("providers", []) or []
    row: dict[str, Any] = {
        "id": row_id or uuid.uuid4().hex[:12],
        "title": clean_text(title),
        "poster_url": clean_text(result.get("poster_url", "")) or clean_text(existing_poster_url),
        "btv_update_date": str(update_date),
        "content_type": clean_text(content_type) or clean_text(result.get("content_type", "")) or "기타",
        "open_year": clean_text(open_year),
        "matched_title": clean_text(result.get("matched_title", "")),
        "matched_year": clean_text(result.get("matched_year", "")),
        "source_url": clean_text(result.get("source_url", "")),
        "other_providers": ", ".join([name for name in providers if name not in OTT_COLUMNS]),
        "lookup_status": clean_text(result.get("status", "조회 실패")),
        "last_checked": now_kst_text(),
    }
    for provider_name, column in OTT_COLUMNS.items():
        row[column] = provider_name in providers
    return row


# -----------------------------------------------------------------------------
# Admin / actions
# -----------------------------------------------------------------------------
def is_admin() -> bool:
    password = secret_value("ADMIN_PASSWORD")
    if not password:
        return True
    return bool(st.session_state.get("admin_authenticated", False))


def render_admin_login() -> None:
    password = secret_value("ADMIN_PASSWORD")
    if not password or is_admin():
        return
    with st.sidebar:
        st.subheader("관리자 로그인")
        entered = st.text_input("관리 비밀번호", type="password")
        if st.button("로그인", use_container_width=True):
            if entered == password:
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("비밀번호가 맞지 않습니다.")


def fetch_refresh_result(target: Any) -> dict[str, Any]:
    lookup_kinolights.clear()
    lookup_selected_kinolights.clear()
    saved_candidate = {
        "title": clean_text(target.get("matched_title", "")) or clean_text(target.get("title", "")),
        "poster_url": clean_text(target.get("poster_url", "")),
        "url": clean_text(target.get("source_url", "")),
        "year": clean_text(target.get("matched_year", "")) or clean_text(target.get("open_year", "")),
        "query": clean_text(target.get("title", "")),
    }
    if saved_candidate["url"] and saved_candidate["poster_url"]:
        return lookup_selected_kinolights(json.dumps(saved_candidate, ensure_ascii=False))
    return lookup_kinolights(
        clean_text(target.get("title", "")),
        clean_text(target.get("open_year", "")),
    )


def fetch_refresh_result_in_context(context: Any, target: Any) -> dict[str, Any]:
    """공유 브라우저 컨텍스트에서 저장된 작품을 최신 조회한다.

    일괄 최신화는 작품마다 브라우저를 새로 띄우지 않고 하나의 컨텍스트를
    재사용해 처리 시간을 줄인다. 캐시를 거치지 않으므로 현재 시점 정보를 조회한다.
    """
    title = clean_text(target.get("matched_title", "")) or clean_text(target.get("title", ""))
    candidate = {
        "title": title,
        "poster_url": clean_text(target.get("poster_url", "")),
        "url": clean_text(target.get("source_url", "")),
        "year": clean_text(target.get("matched_year", "")) or clean_text(target.get("open_year", "")),
        "content_type": clean_text(target.get("content_type", "")),
        "query": clean_text(target.get("title", "")) or title,
    }
    try:
        result = inspect_selected_candidate(context, candidate)
        status = clean_text(result.get("status", "조회 완료"))
        hard_failure = status in {
            "상세 페이지 이동 실패",
            "상세 작품 검증 실패",
        }
        return {
            "ok": not hard_failure,
            "status": status,
            "providers": result.get("providers", []) or [],
            "matched_title": title,
            "matched_year": clean_text(result.get("year", "")),
            "content_type": clean_text(result.get("content_type", ""))
            or clean_text(target.get("content_type", ""))
            or "기타",
            "source_url": clean_text(result.get("source_url", ""))
            or clean_text(target.get("source_url", "")),
            "poster_url": clean_text(target.get("poster_url", "")),
        }
    except PlaywrightTimeoutError:
        return {"ok": False, "status": "OTT 조회 시간 초과", "providers": []}
    except Exception as exc:
        return {
            "ok": False,
            "status": f"OTT 조회 오류: {str(exc)[:80]}",
            "providers": [],
        }


def result_preview_html(label: str, providers: list[str]) -> str:
    provider_set = set(providers)
    badges = []
    for provider in OTT_COLUMNS:
        mark = "O" if provider in provider_set else "X"
        color = "#159b2b" if mark == "O" else "#e52a3d"
        badges.append(
            f'<span style="display:inline-block;min-width:74px;margin:3px 4px 3px 0;'
            f'padding:6px 8px;border:1px solid #e1e5ef;border-radius:8px;background:white;'
            f'font-size:11px;font-weight:800">{html.escape(provider)} '
            f'<b style="color:{color};font-size:15px">{mark}</b></span>'
        )
    return (
        f'<div class="dialog-summary"><b>{html.escape(label)}</b><br>'
        + "".join(badges)
        + "</div>"
    )


def handle_query_actions(df: pd.DataFrame) -> None:
    if not is_admin():
        return
    refresh_id = clean_text(st.query_params.get("refresh", ""))
    delete_id = clean_text(st.query_params.get("delete", ""))
    if not refresh_id and not delete_id:
        return

    if refresh_id:
        st.session_state["_pending_management_dialog"] = {
            "action": "refresh",
            "row_id": refresh_id,
        }
    elif delete_id:
        st.session_state["_pending_management_dialog"] = {
            "action": "delete",
            "row_id": delete_id,
        }
    # 같은 실행 흐름에서 팝업을 열어 불필요한 전체 재실행을 줄인다.
    st.query_params.clear()


@st.dialog("OTT 정보 다시 확인")
def render_refresh_dialog(df: pd.DataFrame, row_id: str) -> None:
    matches = df.index[df["id"].astype(str) == row_id].tolist()
    if not matches:
        st.error("재확인할 콘텐츠를 찾지 못했습니다.")
        return

    index = matches[0]
    target = df.loc[index]
    title = clean_text(target.get("title", ""))
    current_providers = [
        provider for provider, column in OTT_COLUMNS.items() if as_bool(target.get(column, False))
    ]
    st.markdown(f"**{html.escape(title)}**의 OTT 제공처를 다시 확인합니다.")
    st.markdown(result_preview_html("현재 저장값", current_providers), unsafe_allow_html=True)
    st.caption("새 조회에 실패하면 현재 저장값은 변경하지 않습니다.")

    preview_key = f"_refresh_preview_{row_id}"
    preview = st.session_state.get(preview_key)

    if st.button("최신 정보 불러오기", type="primary", use_container_width=True):
        with st.spinner(f"'{title}'의 최신 OTT 정보를 확인하고 있습니다…"):
            preview = fetch_refresh_result(target)
        st.session_state[preview_key] = preview

    if preview:
        if not preview.get("ok"):
            st.error(
                "최신 정보를 불러오지 못했습니다. 기존 저장값은 그대로 유지됩니다. "
                + clean_text(preview.get("status", ""))
            )
        else:
            new_providers = preview.get("providers", []) or []
            st.markdown(result_preview_html("새 조회 결과", new_providers), unsafe_allow_html=True)
            st.caption(clean_text(preview.get("status", "")))

            suspicious_empty = bool(current_providers) and not new_providers
            allow_empty = True
            if suspicious_empty:
                st.markdown(
                    '<div class="dialog-warning">기존에는 O가 있었지만 새 결과가 모두 X입니다. '
                    '키노라이츠 개편이나 일시적 조회 실패일 수 있어 기본적으로 저장을 막았습니다.</div>',
                    unsafe_allow_html=True,
                )
                allow_empty = st.checkbox("모두 X인 결과로 덮어쓰겠습니다")

            if st.button(
                "이 결과로 저장",
                type="primary",
                use_container_width=True,
                disabled=not allow_empty,
            ):
                parsed_date = pd.to_datetime(target.get("btv_update_date"), errors="coerce")
                update_date = parsed_date.date() if pd.notna(parsed_date) else date.today()
                replacement = result_to_row(
                    title=title,
                    update_date=update_date,
                    content_type=clean_text(target.get("content_type", "")),
                    open_year=clean_text(target.get("open_year", "")),
                    result=preview,
                    row_id=row_id,
                    existing_poster_url=clean_text(target.get("poster_url", "")),
                )
                updated = df.copy()
                for key, value in replacement.items():
                    updated.at[index, key] = value
                history_event = make_history_event(
                    "재확인",
                    replacement,
                    previous_row=target,
                    note="관리 팝업에서 새 조회 결과 저장",
                )
                try:
                    warning = save_data(
                        updated,
                        f"Refresh OTT providers: {title}",
                        [history_event],
                    )
                    st.session_state.pop(preview_key, None)
                    if warning:
                        st.session_state["_flash_warning"] = warning
                    else:
                        st.session_state["_flash_toast"] = "새 조회 결과를 저장했습니다."
                    st.rerun()
                except Exception as exc:
                    st.error(f"저장하지 못했습니다: {exc}")

    if st.button("닫기", use_container_width=True):
        st.session_state.pop(preview_key, None)
        st.rerun()


@st.dialog("전체 OTT 정보 일괄 업데이트")
def render_bulk_refresh_all_dialog(df: pd.DataFrame) -> None:
    source_df = normalize_dataframe(df).copy()
    total = len(source_df)
    if source_df.empty:
        st.info("업데이트할 콘텐츠가 없습니다.")
        if st.button("닫기", use_container_width=True, key="close_empty_bulk_refresh"):
            st.rerun()
        return

    st.markdown(
        f'<div class="dialog-summary"><b>등록 콘텐츠 {total:,}개</b>의 키노라이츠 OTT 제공처를 '
        '현재 시점 기준으로 다시 확인합니다.<br>'
        '조회가 실패한 콘텐츠는 기존 저장값을 유지하고, 기존 O가 모두 X로 조회된 경우도 '
        '안전을 위해 자동 덮어쓰지 않습니다.</div>',
        unsafe_allow_html=True,
    )
    st.caption("콘텐츠 수에 따라 시간이 걸릴 수 있습니다. 완료될 때까지 창을 닫지 마세요.")

    if st.button(
        "전체 콘텐츠 최신 정보 확인 및 저장",
        type="primary",
        use_container_width=True,
        key="run_bulk_refresh_all",
    ):
        progress = st.progress(0, text="일괄 업데이트를 시작합니다…")
        status_box = st.empty()
        updated = source_df.copy()
        history_events: list[dict[str, Any]] = []
        refreshed_count = 0
        changed_count = 0
        unchanged_count = 0
        failed_titles: list[str] = []
        protected_titles: list[str] = []

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(**browser_launch_kwargs())
                context = browser.new_context(
                    viewport={"width": 430, "height": 1600},
                    locale="ko-KR",
                    timezone_id="Asia/Seoul",
                    user_agent=(
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                        "Mobile/15E148 Safari/604.1"
                    ),
                )

                for position, (index, target) in enumerate(source_df.iterrows(), start=1):
                    title = clean_text(target.get("title", ""))
                    status_box.caption(f"{position}/{total} · {title} 확인 중")
                    result = fetch_refresh_result_in_context(context, target)
                    current_providers = {
                        provider
                        for provider, column in OTT_COLUMNS.items()
                        if as_bool(target.get(column, False))
                    }

                    if not result.get("ok"):
                        failed_titles.append(title)
                    else:
                        new_providers = set(result.get("providers", []) or [])
                        # 기존에 O가 있었는데 새 결과가 모두 X이면 크롤러 이상 가능성이 있어 보호한다.
                        if current_providers and not new_providers:
                            protected_titles.append(title)
                        else:
                            parsed_date = pd.to_datetime(
                                target.get("btv_update_date"), errors="coerce"
                            )
                            update_date = (
                                parsed_date.date() if pd.notna(parsed_date) else date.today()
                            )
                            replacement = result_to_row(
                                title=title,
                                update_date=update_date,
                                content_type=clean_text(target.get("content_type", "")),
                                open_year=clean_text(target.get("open_year", "")),
                                result=result,
                                row_id=clean_text(target.get("id", "")),
                                existing_poster_url=clean_text(target.get("poster_url", "")),
                            )
                            for key, value in replacement.items():
                                updated.at[index, key] = value

                            changed = current_providers != new_providers
                            if changed:
                                changed_count += 1
                            else:
                                unchanged_count += 1
                            refreshed_count += 1
                            history_events.append(
                                make_history_event(
                                    "일괄 재확인",
                                    replacement,
                                    previous_row=target,
                                    note=(
                                        "전체 최신화 · OTT 편성 변경"
                                        if changed
                                        else "전체 최신화 · 편성 변경 없음"
                                    ),
                                )
                            )

                    progress.progress(
                        position / total,
                        text=f"{position}/{total} · {title} 확인 완료",
                    )

                context.close()
                browser.close()

            if refreshed_count:
                warning = save_data(
                    updated,
                    f"Bulk refresh OTT providers: {refreshed_count}/{total} items",
                    history_events,
                )
                summary = (
                    f"전체 최신화 완료: 확인 {refreshed_count}개 · 변경 {changed_count}개 · "
                    f"변경 없음 {unchanged_count}개"
                )
                if failed_titles or protected_titles:
                    detail_parts = []
                    if failed_titles:
                        detail_parts.append(f"조회 실패 {len(failed_titles)}개")
                    if protected_titles:
                        detail_parts.append(f"모두 X 결과 보호 {len(protected_titles)}개")
                    st.session_state["_flash_warning"] = (
                        summary + " · " + " · ".join(detail_parts)
                    )
                elif warning:
                    st.session_state["_flash_warning"] = summary + " · " + warning
                else:
                    st.session_state["_flash_toast"] = summary
                st.rerun()
            else:
                st.error(
                    "저장 가능한 최신 조회 결과가 없습니다. 기존 값은 모두 그대로 유지했습니다."
                )
                if failed_titles:
                    st.caption("조회 실패: " + ", ".join(failed_titles[:10]))
                if protected_titles:
                    st.caption(
                        "모두 X로 조회되어 보호한 콘텐츠: "
                        + ", ".join(protected_titles[:10])
                    )
        except Exception as exc:
            st.error(f"전체 최신화를 완료하지 못했습니다. 기존 저장값은 유지됩니다: {exc}")

    if st.button("닫기", use_container_width=True, key="close_bulk_refresh_all"):
        st.rerun()


@st.dialog("콘텐츠 삭제")
def render_delete_dialog(df: pd.DataFrame, row_id: str) -> None:
    matches = df[df["id"].astype(str) == row_id]
    if matches.empty:
        st.error("삭제할 콘텐츠를 찾지 못했습니다.")
        return
    target = matches.iloc[0]
    title = clean_text(target.get("title", ""))
    st.markdown(f"**{html.escape(title)}**을(를) 목록에서 삭제할까요?")
    st.markdown(
        '<div class="dialog-warning">목록에서는 삭제되지만, 삭제 직전 데이터는 저장 기록에 남습니다.</div>',
        unsafe_allow_html=True,
    )
    yes_col, no_col = st.columns(2)
    with yes_col:
        if st.button("삭제", type="primary", use_container_width=True):
            updated = df[df["id"].astype(str) != row_id].copy()
            history_event = make_history_event(
                "삭제",
                target,
                note="삭제 직전 데이터 보관",
            )
            try:
                warning = save_data(
                    updated,
                    f"Delete B tv+ content: {title}",
                    [history_event],
                )
                if warning:
                    st.session_state["_flash_warning"] = warning
                else:
                    st.session_state["_flash_toast"] = "삭제했습니다. 삭제 직전 값은 저장 기록에 남았습니다."
                st.rerun()
            except Exception as exc:
                st.error(f"삭제하지 못했습니다: {exc}")
    with no_col:
        if st.button("취소", use_container_width=True):
            st.rerun()


def render_pending_management_dialog(df: pd.DataFrame) -> None:
    pending = st.session_state.pop("_pending_management_dialog", None)
    if not pending or not is_admin():
        return
    action = clean_text(pending.get("action", ""))
    row_id = clean_text(pending.get("row_id", ""))
    if action == "refresh":
        render_refresh_dialog(df, row_id)
    elif action == "delete":
        render_delete_dialog(df, row_id)


@st.dialog("이미 등록된 콘텐츠")
def render_duplicate_content_dialog(title: str) -> None:
    st.markdown(
        f'<div class="dialog-summary"><b>{html.escape(title)}</b>은(는) 이미 등록되어 있습니다.<br>'
        '목록에서 기존 콘텐츠를 재확인하거나 삭제한 뒤 다시 추가해 주세요.</div>',
        unsafe_allow_html=True,
    )
    spacer, close_col = st.columns([4, 1])
    with close_col:
        if st.button("닫기", type="primary", use_container_width=True, key="close_duplicate_dialog"):
            st.rerun()


@st.dialog("저장 기록")
def render_history_dialog(df: pd.DataFrame, history_df: pd.DataFrame) -> None:
    cfg = github_config()
    storage_label = "GitHub 영구 저장" if cfg else "앱 서버 임시 저장"
    st.markdown(
        f'<div class="dialog-summary"><span class="history-status">{storage_label}</span><br>'
        f'현재 콘텐츠 <b>{len(df):,}건</b> · 변경 기록 <b>{len(history_df):,}건</b></div>',
        unsafe_allow_html=True,
    )

    if not cfg:
        st.warning(
            "현재는 앱 서버에만 저장됩니다. Streamlit 재배포·재시작 시 사라질 수 있으므로 "
            "GitHub Secrets 연결 또는 아래 백업 ZIP 다운로드가 필요합니다."
        )

    if st.button("현재 목록을 기록으로 저장", use_container_width=True):
        events = [
            make_history_event("수동 백업", row, note="현재 목록 스냅샷")
            for _, row in df.iterrows()
        ]
        if not events:
            st.info("저장할 콘텐츠가 없습니다.")
        else:
            try:
                append_history_events(events, "Manual snapshot of current B tv+ contents")
                st.success(f"현재 콘텐츠 {len(events):,}건을 저장 기록에 추가했습니다.")
                time.sleep(0.3)
                st.rerun()
            except Exception as exc:
                st.error(f"저장 기록을 남기지 못했습니다: {exc}")

    latest_history = load_history()
    if latest_history.empty:
        st.caption("아직 저장 기록이 없습니다.")
    else:
        display = latest_history.copy()
        display = display.sort_values("timestamp", ascending=False).head(20)
        display = display[["timestamp", "action", "title", "ott_summary", "note"]]
        display.columns = ["일시", "구분", "타이틀", "OTT 저장값", "메모"]
        st.dataframe(display, use_container_width=True, hide_index=True)

    history_csv = normalize_history_dataframe(latest_history).to_csv(index=False).encode("utf-8-sig")
    backup_zip = build_backup_zip(df, latest_history)
    download_col, backup_col = st.columns(2)
    with download_col:
        st.download_button(
            "변경 기록 CSV",
            data=history_csv,
            file_name=f"btv_max_history_{date.today()}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with backup_col:
        st.download_button(
            "전체 백업 ZIP",
            data=backup_zip,
            file_name=f"btv_max_backup_{date.today()}.zip",
            mime="application/zip",
            use_container_width=True,
        )


# -----------------------------------------------------------------------------
# Table rendering
# -----------------------------------------------------------------------------
def placeholder_poster(title: str) -> str:
    initial = html.escape(clean_text(title)[:1] or "B")
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='132' height='188'>
      <defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0' stop-color='#081b61'/><stop offset='1' stop-color='#2848a0'/></linearGradient></defs>
      <rect width='132' height='188' rx='10' fill='url(#g)'/>
      <text x='66' y='91' text-anchor='middle' fill='white' font-size='42' font-family='Arial' font-weight='700'>{initial}</text>
      <text x='66' y='119' text-anchor='middle' fill='#d9e3ff' font-size='12' font-family='Arial'>B tv+ max</text>
    </svg>
    """
    return "data:image/svg+xml;charset=UTF-8," + quote(svg)


def poster_html(row: pd.Series) -> str:
    fallback = placeholder_poster(clean_text(row.get("title", "")))
    poster = clean_text(row.get("poster_url", "")) or fallback
    return (
        f'<img class="poster" src="{html.escape(poster, quote=True)}" '
        f'onerror="this.onerror=null;this.src=\'{fallback}\';" alt="포스터">'
    )


def type_badge(content_type: str) -> str:
    label = clean_text(content_type) or "기타"
    css_map = {
        "드라마": "type-drama",
        "영화": "type-movie",
        "예능": "type-variety",
        "애니": "type-ani",
        "키즈": "type-kids",
    }
    css_class = css_map.get(label, "type-etc")
    return f'<span class="type-badge {css_class}">{html.escape(label)}</span>'


def ox_badge(value: Any) -> str:
    return '<span class="ox-o">O</span>' if as_bool(value) else '<span class="ox-x">X</span>'


BULK_SELECTION_PREFIX = "bulk_row_select_"


def selected_content_ids(full_df: pd.DataFrame) -> list[str]:
    """현재 세션에서 선택된 유효 콘텐츠 ID를 반환한다."""
    valid_ids = set(full_df["id"].astype(str).tolist()) if not full_df.empty else set()
    selected: list[str] = []
    for key, value in list(st.session_state.items()):
        if not key.startswith(BULK_SELECTION_PREFIX):
            continue
        row_id = key[len(BULK_SELECTION_PREFIX) :]
        if row_id in valid_ids and bool(value):
            selected.append(row_id)
        elif row_id not in valid_ids:
            st.session_state.pop(key, None)
    return selected


def clear_bulk_selection(row_ids: list[str] | None = None) -> None:
    targets = set(row_ids or [])
    for key in list(st.session_state.keys()):
        if not key.startswith(BULK_SELECTION_PREFIX):
            continue
        row_id = key[len(BULK_SELECTION_PREFIX) :]
        if not targets or row_id in targets:
            st.session_state.pop(key, None)


@st.dialog("선택 콘텐츠 일괄 삭제")
def render_bulk_delete_dialog(full_df: pd.DataFrame, row_ids: list[str]) -> None:
    row_ids = [clean_text(value) for value in row_ids if clean_text(value)]
    targets = full_df[full_df["id"].astype(str).isin(row_ids)].copy()
    if targets.empty:
        st.error("삭제할 콘텐츠를 찾지 못했습니다.")
        return

    titles = [clean_text(value) for value in targets["title"].tolist()]
    preview = "<br>".join(f"• {html.escape(title)}" for title in titles[:12])
    if len(titles) > 12:
        preview += f"<br>• 외 {len(titles) - 12}개"
    st.markdown(
        f'<div class="dialog-summary"><b>총 {len(titles)}개 콘텐츠</b><br>{preview}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="dialog-warning">선택한 콘텐츠를 목록에서 일괄 삭제합니다. '
        '삭제 직전 값은 저장 기록에 각각 남습니다.</div>',
        unsafe_allow_html=True,
    )

    yes_col, no_col = st.columns(2)
    with yes_col:
        if st.button("선택 항목 삭제", type="primary", use_container_width=True):
            updated = full_df[~full_df["id"].astype(str).isin(row_ids)].copy()
            history_events = [
                make_history_event("일괄 삭제", row, note="체크박스 선택 후 일괄 삭제")
                for _, row in targets.iterrows()
            ]
            try:
                warning = save_data(
                    updated,
                    f"Bulk delete B tv+ contents: {len(targets)} items",
                    history_events,
                )
                clear_bulk_selection(row_ids)
                if warning:
                    st.session_state["_flash_warning"] = warning
                else:
                    st.session_state["_flash_toast"] = (
                        f"선택한 {len(targets)}개 콘텐츠를 삭제했습니다."
                    )
                st.rerun()
            except Exception as exc:
                st.error(f"일괄 삭제하지 못했습니다: {exc}")
    with no_col:
        if st.button("취소", use_container_width=True):
            st.rerun()


@st.fragment
def render_table(df: pd.DataFrame, full_df: pd.DataFrame, page_size: int = 30) -> None:
    """필터된 목록을 표시하되 저장·삭제는 전체 데이터 기준으로 처리한다."""
    if df.empty:
        clear_bulk_selection()
        st.markdown(
            '<div class="empty-box"><b>등록된 콘텐츠가 없습니다.</b><br>'
            '<span style="font-size:12px">상단에서 타이틀을 추가하면 포스터와 OTT 편성 여부가 자동 표시됩니다.</span></div>',
            unsafe_allow_html=True,
        )
        return

    total_items = len(df)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    current_page = int(st.session_state.get("content_page", 1))
    current_page = max(1, min(current_page, total_pages))
    st.session_state["content_page"] = current_page
    page_start = (current_page - 1) * page_size
    page_df = df.iloc[page_start : page_start + page_size]
    page_ids = page_df["id"].astype(str).tolist()

    # 선택 상태는 전체 데이터에서 유효한 ID만 유지한다.
    selected_ids = selected_content_ids(full_df)
    selected_set = set(selected_ids)
    page_selected_count = sum(1 for row_id in page_ids if row_id in selected_set)
    all_page_selected = bool(page_ids) and page_selected_count == len(page_ids)

    if selected_ids and is_admin():
        with st.container(key="bulk_action_bar"):
            info_col, clear_col, delete_col = st.columns(
                [4.5, 1.0, 1.25], gap="small", vertical_alignment="center"
            )
            with info_col:
                st.markdown(
                    f'<div class="bulk-selected-text">✓ 선택된 콘텐츠 <b style="margin-left:5px">{len(selected_ids)}개</b></div>',
                    unsafe_allow_html=True,
                )
            with clear_col:
                if st.button("선택 해제", use_container_width=True, key="bulk_clear_button"):
                    clear_bulk_selection()
                    st.rerun(scope="fragment")
            with delete_col:
                if st.button(
                    "선택 항목 삭제",
                    use_container_width=True,
                    key="bulk_delete_button",
                ):
                    render_bulk_delete_dialog(full_df, selected_ids)

    # 선택/번호 열을 추가하고 기존 열 비율은 최대한 유지한다.
    widths = [0.72, 3.35, 1.25, 0.98, 0.88, 0.92, 0.76, 0.86, 1.06, 0.74, 0.96]

    with st.container(key="comparison_table_shell"):
        with st.container(key="comparison_header"):
            header = st.columns(widths, gap="small", vertical_alignment="center")

            with header[0]:
                select_hash = abs(hash("|".join(page_ids))) % 1_000_000
                select_key = (
                    f"bulk_select_all_{current_page}_{select_hash}_{page_selected_count}"
                )
                select_col, no_col = st.columns([0.8, 1.0], gap="small", vertical_alignment="center")
                with select_col:
                    page_toggle = st.checkbox(
                        "현재 페이지 전체 선택",
                        value=all_page_selected,
                        key=select_key,
                        label_visibility="collapsed",
                        disabled=not is_admin(),
                    )
                with no_col:
                    st.markdown('<div class="selection-head">No.</div>', unsafe_allow_html=True)

                if is_admin() and page_toggle != all_page_selected:
                    for row_id in page_ids:
                        st.session_state[f"{BULK_SELECTION_PREFIX}{row_id}"] = page_toggle
                    st.rerun(scope="fragment")

            header_labels = [
                '<div class="native-head left">포스터 · 타이틀명</div>',
                '<div class="native-head">B tv+ 업데이트일</div>',
                '<div class="native-head">콘텐츠 구분</div>',
                '<div class="native-head"><span class="provider-n">N</span>넷플릭스</div>',
                '<div class="native-head"><span class="provider-c">▶</span>쿠팡플레이</div>',
                '<div class="native-head"><span class="provider-t">T</span>티빙</div>',
                '<div class="native-head"><span class="provider-w">W</span>웨이브</div>',
                '<div class="native-head"><span class="provider-d">Disney</span> 디즈니+</div>',
                '<div class="native-head"><span class="provider-wa">W</span>왓챠</div>',
                '<div class="native-head">관리</div>',
            ]
            for column, label in zip(header[1:], header_labels):
                with column:
                    st.markdown(label, unsafe_allow_html=True)

        for page_offset, (_, row) in enumerate(page_df.iterrows()):
            title = clean_text(row.get("title", ""))
            matched_title = clean_text(row.get("matched_title", ""))
            matched_year = clean_text(row.get("matched_year", ""))
            source_url = clean_text(row.get("source_url", ""))
            open_year = clean_text(row.get("open_year", ""))
            last_checked = clean_text(row.get("last_checked", ""))
            row_id = clean_text(row.get("id", ""))
            absolute_no = page_start + page_offset + 1

            details: list[str] = []
            if open_year:
                details.append(open_year)
            if matched_title and normalize_title(matched_title) != normalize_title(title):
                details.append(f"매칭: {matched_title}")
            elif matched_year and matched_year not in details:
                details.append(matched_year)
            if last_checked:
                details.append(f"확인 {last_checked}")

            detail_text = " · ".join(html.escape(item) for item in details)
            if source_url:
                source_link = (
                    f'<a href="{html.escape(source_url, quote=True)}" target="_blank">근거 보기</a>'
                )
                detail_text += (" · " if detail_text else "") + source_link

            with st.container(key=f"content_row_{row_id}"):
                columns = st.columns(widths, gap="small", vertical_alignment="center")

                with columns[0]:
                    checkbox_col, number_col = st.columns(
                        [0.8, 1.0], gap="small", vertical_alignment="center"
                    )
                    with checkbox_col:
                        st.checkbox(
                            f"{title} 선택",
                            key=f"{BULK_SELECTION_PREFIX}{row_id}",
                            label_visibility="collapsed",
                            disabled=not is_admin(),
                        )
                    with number_col:
                        st.markdown(
                            f'<div class="row-number">{absolute_no}</div>',
                            unsafe_allow_html=True,
                        )

                with columns[1]:
                    poster_col, copy_col = st.columns(
                        [0.34, 1.0], gap="small", vertical_alignment="center"
                    )
                    with poster_col:
                        st.markdown(poster_html(row), unsafe_allow_html=True)
                    with copy_col:
                        st.markdown(
                            f'<div class="title-main">{html.escape(title)}</div>'
                            f'<div class="title-sub">{detail_text or "-"}</div>',
                            unsafe_allow_html=True,
                        )

                with columns[2]:
                    st.markdown(
                        f'<div class="native-cell">{html.escape(clean_text(row.get("btv_update_date", "")))}</div>',
                        unsafe_allow_html=True,
                    )
                with columns[3]:
                    st.markdown(
                        f'<div class="native-cell">{type_badge(clean_text(row.get("content_type", "")))}</div>',
                        unsafe_allow_html=True,
                    )

                provider_columns = ["netflix", "coupang", "tving", "wavve", "disney", "watcha"]
                for column, provider_column in zip(columns[4:10], provider_columns):
                    with column:
                        st.markdown(
                            f'<div class="native-cell native-ox">{ox_badge(row.get(provider_column))}</div>',
                            unsafe_allow_html=True,
                        )

                with columns[10]:
                    if is_admin():
                        refresh_col, delete_col = st.columns(2, gap="small")
                        with refresh_col:
                            if st.button(
                                "↻",
                                key=f"native_refresh_{row_id}",
                                help=f"{title} 다시 확인",
                                use_container_width=True,
                            ):
                                render_refresh_dialog(full_df, row_id)
                        with delete_col:
                            if st.button(
                                "⌫",
                                key=f"native_delete_{row_id}",
                                help=f"{title} 삭제",
                                use_container_width=True,
                            ):
                                render_delete_dialog(full_df, row_id)
                    else:
                        st.markdown('<div class="native-cell">-</div>', unsafe_allow_html=True)

    if total_pages > 1:
        left, prev_col, info_col, next_col, right = st.columns(
            [3.5, 0.75, 1.4, 0.75, 3.5], vertical_alignment="center"
        )
        with prev_col:
            if st.button(
                "‹ 이전",
                disabled=current_page <= 1,
                use_container_width=True,
                key="page_prev",
            ):
                st.session_state["content_page"] = current_page - 1
                st.rerun(scope="fragment")
        with info_col:
            st.markdown(
                f'<div class="pagination-info">{current_page} / {total_pages} 페이지 · 총 {total_items:,}개</div>',
                unsafe_allow_html=True,
            )
        with next_col:
            if st.button(
                "다음 ›",
                disabled=current_page >= total_pages,
                use_container_width=True,
                key="page_next",
            ):
                st.session_state["content_page"] = current_page + 1
                st.rerun(scope="fragment")


# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
render_admin_login()
df = load_data()
history_df = load_history()

# 저장 완료 메시지는 화면을 잠시 멈추지 않고 다음 실행에서 가볍게 표시한다.
flash_warning = st.session_state.pop("_flash_warning", "")
flash_toast = st.session_state.pop("_flash_toast", "")
if flash_warning:
    st.warning(flash_warning)
if flash_toast:
    try:
        st.toast(flash_toast, icon="✅")
    except Exception:
        st.success(flash_toast)

last_update = "-"
if not df.empty:
    checked = [clean_text(value) for value in df["last_checked"].tolist() if clean_text(value)]
    if checked:
        last_update = sorted(checked, reverse=True)[0]

st.markdown(
    f"""
<div class="topbar">
  <div class="brand">
    <span class="brand-main">B tv+ max</span>
    <span class="brand-sub">콘텐츠 경쟁력 비교 대시보드</span>
  </div>
  <div class="update-pill">마지막 업데이트 {html.escape(last_update)}</div>
</div>
""",
    unsafe_allow_html=True,
)

intro_col, guide_col, history_col, csv_col = st.columns([5.8, 1.05, 1.05, 1.2], vertical_alignment="center")
with intro_col:
    st.markdown(
        """
<div class="intro">
  <div class="intro-title">🎬 B tv+ 업데이트 콘텐츠 OTT 편성 현황</div>
  <div class="intro-sub">B tv+에 업데이트되는 콘텐츠가 주요 OTT에 편성되어 있는지 확인할 수 있습니다. <b style="color:#173b9b">v17 · 정액제 건수 검증형</b></div>
</div>
""",
        unsafe_allow_html=True,
    )
with guide_col:
    if st.button("❔ 사용 가이드", use_container_width=True):
        st.session_state.show_guide = not st.session_state.get("show_guide", False)
with history_col:
    if st.button("🕘 저장 기록", use_container_width=True):
        render_history_dialog(df, history_df)
with csv_col:
    export_df = normalize_dataframe(df)
    st.download_button(
        "⇩ CSV 다운로드",
        data=export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"btv_max_ott_{date.today()}.csv",
        mime="text/csv",
        use_container_width=True,
    )

if st.session_state.get("show_guide", False):
    st.markdown(
        '<div class="guide-box">① 타이틀을 검색합니다. '
        '② 검색 결과에서 정확한 작품을 선택해 추가합니다. '
        '③ 선택한 작품의 포스터와 OTT 제공처를 확인합니다. '
        '④ O는 해당 OTT 편성 확인, X는 편성 미확인입니다. ⑤ 행 우측의 ↻는 재조회, ⌫는 삭제입니다.</div>',
        unsafe_allow_html=True,
    )

if is_admin():
    with st.container(border=True, key="new_content_search_box"):
        st.markdown(
            '<div class="control-title">새 타이틀 검색 및 추가 '
            '<span style="color:#173b9b">(작품 선택 필수)</span></div>',
            unsafe_allow_html=True,
        )
        with st.form("search_content_form", clear_on_submit=False):
            title_col, date_col, search_col = st.columns(
                [3.8, 1.35, 1.25], vertical_alignment="bottom"
            )
            with title_col:
                title_input = st.text_input(
                    "타이틀명",
                    placeholder="타이틀명을 검색하세요",
                    label_visibility="collapsed",
                    key="new_title_search_input",
                )
            with date_col:
                update_date_input = st.date_input(
                    "B tv+ 업데이트일",
                    value=date.today(),
                    label_visibility="collapsed",
                    key="new_title_update_date",
                )
            with search_col:
                search_submitted = st.form_submit_button(
                    "🔍 검색",
                    type="primary",
                    use_container_width=True,
                )

        if search_submitted:
            title_input = clean_text(title_input)
            if not title_input:
                st.error("검색할 타이틀명을 입력하세요.")
            else:
                search_kinolights_candidates.clear()
                with st.spinner(f"'{title_input}' 검색 결과를 확인하고 있습니다…"):
                    candidates = search_kinolights_candidates(title_input)
                candidates = deduplicate_candidates_for_display(candidates)
                st.session_state["content_search_query"] = title_input
                st.session_state["content_search_candidates"] = candidates
                st.session_state["content_search_meta"] = {
                    "update_date": str(update_date_input),
                }
                if not candidates:
                    st.warning("일치하는 검색 결과가 없습니다. 제목을 더 정확하게 입력해 주세요.")

        candidates = deduplicate_candidates_for_display(
            st.session_state.get("content_search_candidates", [])
        )
        if candidates:
            st.markdown(
                f'<div class="search-result-title">검색 결과 '
                f'<span class="search-result-count">{len(candidates)}</span>'
                '<span class="search-result-note">정확한 작품을 선택하세요. 5개 이후는 내부 스크롤됩니다.</span></div>',
                unsafe_allow_html=True,
            )
            meta = st.session_state.get("content_search_meta", {})
            with st.container(height=480, border=True, key="candidate_results_shell"):
                for index, candidate in enumerate(candidates):
                    candidate_title = clean_text(candidate.get("title", ""))
                    candidate_year = clean_text(candidate.get("year", ""))
                    candidate_type = clean_text(candidate.get("content_type", "")) or "자동 확인"
                    candidate_poster = clean_text(candidate.get("poster_url", ""))
                    with st.container(key=f"candidate_row_{index}"):
                        result_cols = st.columns([0.45, 3.6, 1.22], gap="small", vertical_alignment="center")
                        with result_cols[0]:
                            if candidate_poster:
                                st.image(candidate_poster, width=58)
                            else:
                                st.markdown(
                                    f'<img src="{placeholder_poster(candidate_title)}" '
                                    'style="width:58px;height:80px;object-fit:cover;border-radius:7px">',
                                    unsafe_allow_html=True,
                                )
                        with result_cols[1]:
                            meta_text = " · ".join(
                                value for value in (candidate_year, candidate_type) if value
                            )
                            st.markdown(
                                f'<div class="candidate-title">{html.escape(candidate_title)}</div>'
                                f'<div class="candidate-meta">{html.escape(meta_text or "정보 자동 확인")}</div>',
                                unsafe_allow_html=True,
                            )
                        with result_cols[2]:
                            if st.button(
                                "이 콘텐츠 추가",
                                key=f"add_candidate_{index}",
                                use_container_width=True,
                            ):
                                existing_titles = (
                                    df["title"].apply(normalize_title).tolist() if not df.empty else []
                                )
                                if normalize_title(candidate_title) in existing_titles:
                                    render_duplicate_content_dialog(candidate_title)
                                else:
                                    candidate["query"] = clean_text(
                                        st.session_state.get("content_search_query", candidate_title)
                                    )
                                    with st.spinner(
                                        f"'{candidate_title}'의 OTT 제공처를 확인하고 있습니다…"
                                    ):
                                        result = lookup_selected_kinolights(
                                            json.dumps(candidate, ensure_ascii=False)
                                        )
                                    parsed_date = pd.to_datetime(
                                        meta.get("update_date"), errors="coerce"
                                    )
                                    selected_date = (
                                        parsed_date.date() if pd.notna(parsed_date) else date.today()
                                    )
                                    new_row = result_to_row(
                                        title=candidate_title,
                                        update_date=selected_date,
                                        content_type=clean_text(result.get("content_type", ""))
                                        or candidate_type
                                        or "기타",
                                        open_year=candidate_year,
                                        result=result,
                                    )
                                    updated = pd.concat(
                                        [df, pd.DataFrame([new_row])], ignore_index=True
                                    )
                                    try:
                                        history_event = make_history_event(
                                            "추가",
                                            new_row,
                                            note="검색 결과에서 작품 선택 후 추가",
                                        )
                                        warning = save_data(
                                            updated,
                                            f"Add B tv+ content: {candidate_title}",
                                            [history_event],
                                        )
                                        clear_content_search_results()
                                        if warning:
                                            st.session_state["_flash_warning"] = warning
                                        else:
                                            st.session_state["_flash_toast"] = (
                                                f"'{candidate_title}'을(를) 추가했습니다."
                                            )
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(f"저장하지 못했습니다: {exc}")

            close_space, close_col = st.columns([5.2, 1.0], vertical_alignment="center")
            with close_col:
                if st.button(
                    "검색 결과 닫기",
                    key="search_results_close",
                    use_container_width=True,
                ):
                    clear_content_search_results()
                    st.rerun()
else:
    st.caption("추가·재조회·삭제 기능은 관리자 로그인 후 사용할 수 있습니다.")

# 등록된 데이터의 실제 월 범위만 연월 필터에 노출한다.
month_values: list[str] = []
if not df.empty:
    valid_dates = pd.to_datetime(df["btv_update_date"], errors="coerce").dropna()
    if not valid_dates.empty:
        month_values = [period.strftime("%Y-%m") for period in pd.period_range(
            valid_dates.min().to_period("M"), valid_dates.max().to_period("M"), freq="M"
        )]
month_options = ["전체"] + month_values
month_label = lambda value: "전체" if value == "전체" else f"{value[:4]}년 {value[5:7]}월"

# 위젯 상태가 현재 옵션에서 벗어난 경우 안전하게 초기화한다.
type_values = ["전체"]
if not df.empty:
    present_types = sorted(
        {clean_text(value) for value in df["content_type"].tolist() if clean_text(value)}
    )
    type_values += present_types
if st.session_state.get("content_type_filter", "전체") not in type_values:
    st.session_state["content_type_filter"] = "전체"
for month_key in ("start_month_filter", "end_month_filter"):
    if st.session_state.get(month_key, "전체") not in month_options:
        st.session_state[month_key] = "전체"

with st.container(border=True, key="content_filter_toolbar"):
    search_col, type_col, start_col, tilde_col, end_col, reset_col, refresh_col, storage_col = st.columns(
        [2.28, 0.78, 0.94, 0.12, 0.94, 0.74, 1.02, 1.04],
        gap="small",
        vertical_alignment="center",
    )
    with search_col:
        search_text = st.text_input(
            "타이틀 검색",
            placeholder="등록 타이틀 검색",
            label_visibility="collapsed",
            key="content_title_filter",
        )
    with type_col:
        type_filter = st.selectbox(
            "장르",
            type_values,
            label_visibility="collapsed",
            key="content_type_filter",
        )
    with start_col:
        start_month = st.selectbox(
            "시작 연월",
            month_options,
            format_func=month_label,
            label_visibility="collapsed",
            key="start_month_filter",
        )
    with tilde_col:
        st.markdown('<div class="filter-tilde">~</div>', unsafe_allow_html=True)
    with end_col:
        end_month = st.selectbox(
            "종료 연월",
            month_options,
            format_func=month_label,
            label_visibility="collapsed",
            key="end_month_filter",
        )
    with reset_col:
        st.button(
            "↺ 초기화",
            key="reset_content_filters",
            use_container_width=True,
            on_click=reset_content_filters,
        )
    with refresh_col:
        if st.button(
            "⟳ 전체 최신화",
            key="bulk_refresh_all",
            use_container_width=True,
            disabled=df.empty or not is_admin(),
            help="등록된 모든 콘텐츠의 키노라이츠 OTT 편성정보를 현재 시점 기준으로 다시 확인합니다.",
        ):
            render_bulk_refresh_all_dialog(df)
    with storage_col:
        if github_config():
            st.markdown(
                '<div class="storage-pill"><span class="storage-dot"></span>GitHub 영구 저장</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="storage-pill temporary"><span class="storage-dot temp"></span>임시 저장 · 재배포 시 초기화</div>',
                unsafe_allow_html=True,
            )

if not github_config():
    st.caption("⚠ 현재는 Streamlit 실행 서버에만 임시 저장됩니다. 재배포해도 유지하려면 GitHub 영구 저장 설정이 필요합니다.")

view = df.copy()
if not view.empty:
    if search_text:
        query = normalize_title(search_text)
        view = view[view["title"].apply(normalize_title).str.contains(query, na=False)]
    if type_filter != "전체":
        view = view[view["content_type"] == type_filter]

    view["_date"] = pd.to_datetime(view["btv_update_date"], errors="coerce")
    effective_start, effective_end = start_month, end_month
    if effective_start != "전체" and effective_end != "전체" and effective_start > effective_end:
        effective_start, effective_end = effective_end, effective_start
        st.info("시작 연월이 종료 연월보다 늦어 두 값을 바꿔 적용했습니다.")
    if effective_start != "전체":
        view = view[view["_date"] >= pd.Timestamp(f"{effective_start}-01")]
    if effective_end != "전체":
        end_boundary = pd.Timestamp(f"{effective_end}-01") + pd.offsets.MonthEnd(1)
        view = view[view["_date"] <= end_boundary]

    view = view.sort_values(["_date", "title"], ascending=[False, True]).drop(columns=["_date"])

filter_signature = (search_text, type_filter, start_month, end_month)
if st.session_state.get("_content_filter_signature") != filter_signature:
    st.session_state["_content_filter_signature"] = filter_signature
    st.session_state["content_page"] = 1
    clear_bulk_selection()

render_table(view, full_df=df, page_size=30)
st.markdown(
    '<div class="footer-note">※ OTT 편성 현황은 키노라이츠 정액제 탭의 건수와 실제 제공처가 일치할 때만 반영합니다. '
    '실제 서비스 편성 변경이나 동명 작품 매칭에 따라 차이가 있을 수 있습니다. 저장된 값은 자동으로 바뀌지 않으며, 재확인 후 저장할 때만 갱신됩니다.</div>',
    unsafe_allow_html=True,
)
