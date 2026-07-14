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
BUILD_LABEL = "v11 · UI·기간필터·페이지형"
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
.search-result-title { font-size:13px; font-weight:950; color:#18213d; margin:2px 0 8px; }
.search-result-note { color:#747d93; font-size:11px; }
.pagination-info { text-align:center; color:#667087; font-size:12px; padding-top:12px; }
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
    repo = secret_value("GITHUB_REPO")
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
    """정액제 제공처를 텍스트, DOM 속성, 외부 링크 도메인으로 교차 확인한다."""
    # 지연 로딩되는 바로 보기 영역을 표시하기 위해 페이지를 단계적으로 내린다.
    try:
        for ratio in (0.35, 0.7, 1.0):
            page.evaluate("ratio => window.scrollTo(0, Math.max(0, document.body.scrollHeight * ratio))", ratio)
            page.wait_for_timeout(450)
    except Exception:
        pass

    try:
        body_text = clean_text(page.locator("body").inner_text(timeout=8000)) or body_text
    except Exception:
        body_text = clean_text(body_text)

    section = extract_subscription_section(body_text)
    dom_evidence = collect_provider_dom_evidence(page)
    try:
        raw_html = page.content()
    except Exception:
        raw_html = ""

    found: list[str] = []
    evidence_sets = [
        detect_providers(section),
        detect_direct_view_providers(body_text),
        detect_providers(dom_evidence),
        detect_provider_domains(dom_evidence),
        # 원문 HTML에서는 제공처명 자체가 아니라 외부 링크 도메인만 사용해
        # 번들 문자열 때문에 모든 OTT가 잡히는 오탐을 막는다.
        detect_provider_domains(raw_html),
    ]
    for providers in evidence_sets:
        for provider in providers:
            if provider not in found:
                found.append(provider)
    return found


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


@st.fragment
def render_table(df: pd.DataFrame, page_size: int = 30) -> None:
    """기존 표 비율을 유지하면서 관리 버튼만 네이티브 팝업 방식으로 제공한다."""
    if df.empty:
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

    widths = [3.55, 1.28, 1.0, 0.9, 0.94, 0.78, 0.88, 1.08, 0.76, 0.98]

    with st.container(key="comparison_table_shell"):
        with st.container(key="comparison_header"):
            header = st.columns(widths, gap="small", vertical_alignment="center")
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
            for column, label in zip(header, header_labels):
                with column:
                    st.markdown(label, unsafe_allow_html=True)

        for _, row in page_df.iterrows():
            title = clean_text(row.get("title", ""))
            matched_title = clean_text(row.get("matched_title", ""))
            matched_year = clean_text(row.get("matched_year", ""))
            source_url = clean_text(row.get("source_url", ""))
            open_year = clean_text(row.get("open_year", ""))
            last_checked = clean_text(row.get("last_checked", ""))
            row_id = clean_text(row.get("id", ""))

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
                    poster_col, copy_col = st.columns([0.34, 1.0], gap="small", vertical_alignment="center")
                    with poster_col:
                        st.markdown(poster_html(row), unsafe_allow_html=True)
                    with copy_col:
                        st.markdown(
                            f'<div class="title-main">{html.escape(title)}</div>'
                            f'<div class="title-sub">{detail_text or "-"}</div>',
                            unsafe_allow_html=True,
                        )

                with columns[1]:
                    st.markdown(
                        f'<div class="native-cell">{html.escape(clean_text(row.get("btv_update_date", "")))}</div>',
                        unsafe_allow_html=True,
                    )
                with columns[2]:
                    st.markdown(
                        f'<div class="native-cell">{type_badge(clean_text(row.get("content_type", "")))}</div>',
                        unsafe_allow_html=True,
                    )

                provider_columns = ["netflix", "coupang", "tving", "wavve", "disney", "watcha"]
                for column, provider_column in zip(columns[3:9], provider_columns):
                    with column:
                        st.markdown(
                            f'<div class="native-cell native-ox">{ox_badge(row.get(provider_column))}</div>',
                            unsafe_allow_html=True,
                        )

                with columns[9]:
                    if is_admin():
                        refresh_col, delete_col = st.columns(2, gap="small")
                        with refresh_col:
                            if st.button(
                                "↻",
                                key=f"native_refresh_{row_id}",
                                help=f"{title} 다시 확인",
                                use_container_width=True,
                            ):
                                render_refresh_dialog(df, row_id)
                        with delete_col:
                            if st.button(
                                "⌫",
                                key=f"native_delete_{row_id}",
                                help=f"{title} 삭제",
                                use_container_width=True,
                            ):
                                render_delete_dialog(df, row_id)
                    else:
                        st.markdown('<div class="native-cell">-</div>', unsafe_allow_html=True)

    if total_pages > 1:
        left, prev_col, info_col, next_col, right = st.columns([3.5, 0.75, 1.4, 0.75, 3.5], vertical_alignment="center")
        with prev_col:
            if st.button("‹ 이전", disabled=current_page <= 1, use_container_width=True, key="page_prev"):
                st.session_state["content_page"] = current_page - 1
                st.rerun(scope="fragment")
        with info_col:
            st.markdown(
                f'<div class="pagination-info">{current_page} / {total_pages} 페이지 · 총 {total_items:,}개</div>',
                unsafe_allow_html=True,
            )
        with next_col:
            if st.button("다음 ›", disabled=current_page >= total_pages, use_container_width=True, key="page_next"):
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
  <div class="intro-sub">B tv+에 업데이트되는 콘텐츠가 주요 OTT에 편성되어 있는지 확인할 수 있습니다. <b style="color:#173b9b">v11 · UI·기간필터·페이지형</b></div>
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
    with st.container(border=True):
        st.markdown('<div class="control-title">새 타이틀 검색 및 추가 <span style="color:#173b9b">(작품 선택 필수)</span></div>', unsafe_allow_html=True)
        with st.form("search_content_form", clear_on_submit=False):
            title_col, date_col, search_col = st.columns(
                [3.5, 1.35, 1.25], vertical_alignment="bottom"
            )
            with title_col:
                title_input = st.text_input(
                    "타이틀명",
                    placeholder="타이틀명을 검색하세요",
                    label_visibility="collapsed",
                )
            with date_col:
                update_date_input = st.date_input(
                    "B tv+ 업데이트일",
                    value=date.today(),
                    label_visibility="collapsed",
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
                st.session_state["content_search_query"] = title_input
                st.session_state["content_search_candidates"] = candidates
                st.session_state["content_search_meta"] = {
                    "update_date": str(update_date_input),
                }
                if not candidates:
                    st.warning("일치하는 검색 결과가 없습니다. 제목을 더 정확하게 입력해 주세요.")

        candidates = st.session_state.get("content_search_candidates", [])
        if candidates:
            st.markdown(
                '<div class="search-result-title">검색 결과에서 정확한 작품을 선택하세요 '
                '<span class="search-result-note">· 최대 5개가 보이며 아래로 스크롤할 수 있습니다.</span></div>',
                unsafe_allow_html=True,
            )
            meta = st.session_state.get("content_search_meta", {})
            # 검색 결과가 많아도 화면 전체가 늘어나지 않도록 5개 높이에서 스크롤한다.
            with st.container(height=515, border=True):
                for index, candidate in enumerate(candidates):
                    candidate_title = clean_text(candidate.get("title", ""))
                    candidate_year = clean_text(candidate.get("year", ""))
                    candidate_type = clean_text(candidate.get("content_type", "")) or "자동 확인"
                    candidate_poster = clean_text(candidate.get("poster_url", ""))
                    result_cols = st.columns([0.55, 3.2, 1.05], vertical_alignment="center")
                    with result_cols[0]:
                        if candidate_poster:
                            st.image(candidate_poster, width=66)
                    with result_cols[1]:
                        st.markdown(f"**{html.escape(candidate_title)}**")
                        st.caption(" · ".join(value for value in (candidate_year, candidate_type) if value))
                    with result_cols[2]:
                        if st.button("이 콘텐츠 추가", key=f"add_candidate_{index}", use_container_width=True):
                            existing_titles = df["title"].apply(normalize_title).tolist() if not df.empty else []
                            if normalize_title(candidate_title) in existing_titles:
                                st.warning("이미 등록된 타이틀입니다.")
                            else:
                                candidate["query"] = clean_text(st.session_state.get("content_search_query", candidate_title))
                                with st.spinner(f"'{candidate_title}'의 OTT 제공처를 확인하고 있습니다…"):
                                    result = lookup_selected_kinolights(json.dumps(candidate, ensure_ascii=False))
                                parsed_date = pd.to_datetime(meta.get("update_date"), errors="coerce")
                                selected_date = parsed_date.date() if pd.notna(parsed_date) else date.today()
                                new_row = result_to_row(
                                    title=candidate_title,
                                    update_date=selected_date,
                                    content_type=clean_text(result.get("content_type", ""))
                                    or candidate_type
                                    or "기타",
                                    open_year=candidate_year,
                                    result=result,
                                )
                                updated = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
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
                                    st.session_state.pop("content_search_candidates", None)
                                    st.session_state.pop("content_search_query", None)
                                    st.session_state.pop("content_search_meta", None)
                                    if warning:
                                        st.session_state["_flash_warning"] = warning
                                    else:
                                        st.session_state["_flash_toast"] = f"'{candidate_title}'을(를) 추가했습니다."
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"저장하지 못했습니다: {exc}")
                    if index < len(candidates) - 1:
                        st.divider()
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

with st.container(border=True):
    search_col, type_col, start_col, end_col, storage_col = st.columns(
        [2.65, 1.0, 1.08, 1.08, 1.05], vertical_alignment="center"
    )
    with search_col:
        search_text = st.text_input(
            "타이틀 검색",
            placeholder="타이틀 검색",
            label_visibility="collapsed",
        )
    with type_col:
        # 현재 등록된 콘텐츠에 실제로 존재하는 구분만 표시한다.
        type_values = ["전체"]
        if not df.empty:
            present_types = sorted(
                {clean_text(value) for value in df["content_type"].tolist() if clean_text(value)}
            )
            type_values += present_types
        type_filter = st.selectbox(
            "장르",
            type_values,
            label_visibility="collapsed",
        )
    with start_col:
        start_month = st.selectbox(
            "시작 연월",
            month_options,
            format_func=month_label,
            label_visibility="collapsed",
            key="start_month_filter",
        )
    with end_col:
        end_month = st.selectbox(
            "종료 연월",
            month_options,
            format_func=month_label,
            label_visibility="collapsed",
            key="end_month_filter",
        )
    with storage_col:
        storage_text = "GitHub 영구 저장 + 기록" if github_config() else "앱 내 임시 저장"
        st.caption(storage_text)

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

render_table(view, page_size=30)
st.markdown(
    '<div class="footer-note">※ OTT 편성 현황은 키노라이츠 정액제·바로 보기 문구와 외부 재생 링크를 기반으로 합니다. '
    '실제 서비스 편성 변경이나 동명 작품 매칭에 따라 차이가 있을 수 있습니다. 저장된 값은 자동으로 바뀌지 않으며, 재확인 후 저장할 때만 갱신됩니다.</div>',
    unsafe_allow_html=True,
)
