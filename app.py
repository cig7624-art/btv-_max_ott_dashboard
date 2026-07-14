from __future__ import annotations

import base64
import csv
import html
import io
import os
import re
import tempfile
import time
import uuid
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
BUILD_LABEL = "v6 · 정확한 작품 선택형"
BASE_DIR = Path(__file__).resolve().parent
LOCAL_DATA_PATH = BASE_DIR / "btv_max_contents.csv"

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
    }


def github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "btv-max-ott-dashboard",
    }


def read_github_csv(cfg: dict[str, str]) -> pd.DataFrame:
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{cfg['path']}"
    response = requests.get(
        url,
        headers=github_headers(cfg["token"]),
        params={"ref": cfg["branch"]},
        timeout=20,
    )
    if response.status_code == 404:
        return empty_dataframe()
    response.raise_for_status()
    payload = response.json()
    raw = base64.b64decode(payload["content"]).decode("utf-8-sig")
    if not raw.strip():
        return empty_dataframe()
    return normalize_dataframe(pd.read_csv(io.StringIO(raw)))


def write_github_csv(cfg: dict[str, str], df: pd.DataFrame, message: str) -> None:
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{cfg['path']}"
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

    export_df = normalize_dataframe(df)
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


def read_local_csv() -> pd.DataFrame:
    if not LOCAL_DATA_PATH.exists():
        return empty_dataframe()
    try:
        return normalize_dataframe(pd.read_csv(LOCAL_DATA_PATH))
    except pd.errors.EmptyDataError:
        return empty_dataframe()


def write_local_csv(df: pd.DataFrame) -> None:
    export_df = normalize_dataframe(df)
    LOCAL_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Streamlit Cloud의 /tmp와 /mount/src는 서로 다른 파일시스템일 수 있어
    # 임시 파일을 실제 CSV와 같은 폴더에 만든 뒤 원자적으로 교체한다.
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".csv.tmp",
        prefix="btv_max_",
        dir=LOCAL_DATA_PATH.parent,
        delete=False,
        encoding="utf-8-sig",
        newline="",
    ) as temp:
        export_df.to_csv(temp, index=False)
        temp.flush()
        temp_path = Path(temp.name)

    temp_path.replace(LOCAL_DATA_PATH)


@st.cache_data(ttl=15, show_spinner=False)
def load_data() -> pd.DataFrame:
    cfg = github_config()
    if cfg:
        try:
            return read_github_csv(cfg)
        except Exception as exc:
            st.warning(f"GitHub 데이터를 불러오지 못해 앱 내 CSV를 표시합니다: {exc}")
    return read_local_csv()


def save_data(df: pd.DataFrame, message: str) -> None:
    cfg = github_config()
    if cfg:
        write_github_csv(cfg, df, message)
    else:
        write_local_csv(df)
    load_data.clear()


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
    decoded = html.unescape(clean_text(text))
    start_markers = ["정액제", "구독", "스트리밍"]
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
    return section[:5000]


def detect_providers(text: str) -> list[str]:
    lowered = html.unescape(clean_text(text)).lower()
    found: list[str] = []
    for canonical, aliases in PROVIDER_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            found.append(canonical)
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
            rows.push({title, poster_url:poster, url, year});
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
                "query": query,
            }
        )

    return sorted(
        candidates,
        key=lambda item: candidate_score(query, item["title"], "", item.get("year", "")),
        reverse=True,
    )[:8]


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
        section = extract_subscription_section(body_text)
        providers = detect_providers(section) if section else []
        return {
            **candidate,
            "providers": providers,
            "year": extract_year(body_text) or clean_text(candidate.get("year", "")),
            # Keep the selected result image. Never replace it with a generic OG image.
            "poster_url": clean_text(candidate.get("poster_url", "")),
            "source_url": detail.url,
            "status": "조회 완료" if providers else "주요 OTT 제공처 없음",
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
            return {
                "ok": True,
                "status": clean_text(result.get("status", "조회 완료")),
                "providers": result.get("providers", []) or [],
                "matched_title": title,
                "matched_year": clean_text(result.get("year", "")),
                "source_url": clean_text(result.get("source_url", "")),
                "poster_url": clean_text(candidate.get("poster_url", "")),
            }
    except PlaywrightTimeoutError:
        return {
            "ok": True,
            "status": "OTT 조회 시간 초과",
            "providers": [],
            "matched_title": title,
            "matched_year": clean_text(candidate.get("year", "")),
            "source_url": clean_text(candidate.get("url", "")),
            "poster_url": clean_text(candidate.get("poster_url", "")),
        }
    except Exception as exc:
        return {
            "ok": True,
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
        "content_type": clean_text(content_type),
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


def refresh_row(df: pd.DataFrame, row_id: str) -> None:
    matches = df.index[df["id"].astype(str) == row_id].tolist()
    if not matches:
        st.error("재조회할 콘텐츠를 찾지 못했습니다.")
        return
    index = matches[0]
    target = df.loc[index]
    lookup_kinolights.clear()
    with st.spinner(f"'{clean_text(target['title'])}'의 OTT와 포스터를 다시 확인하고 있습니다…"):
        result = lookup_kinolights(
            clean_text(target["title"]),
            clean_text(target.get("open_year", "")),
        )
    parsed_date = pd.to_datetime(target.get("btv_update_date"), errors="coerce")
    update_date = parsed_date.date() if pd.notna(parsed_date) else date.today()
    replacement = result_to_row(
        title=clean_text(target["title"]),
        update_date=update_date,
        content_type=clean_text(target.get("content_type", "")),
        open_year=clean_text(target.get("open_year", "")),
        result=result,
        row_id=row_id,
        existing_poster_url="",
    )
    updated = df.copy()
    for key, value in replacement.items():
        updated.at[index, key] = value
    save_data(updated, f"Refresh OTT providers: {clean_text(target['title'])}")


def handle_query_actions(df: pd.DataFrame) -> None:
    if not is_admin():
        return
    refresh_id = clean_text(st.query_params.get("refresh", ""))
    delete_id = clean_text(st.query_params.get("delete", ""))

    if delete_id:
        st.session_state.pending_delete_id = delete_id
        st.query_params.clear()
        st.rerun()

    if refresh_id:
        try:
            refresh_row(df, refresh_id)
            st.query_params.clear()
            st.success("OTT 편성 정보와 포스터를 다시 확인했습니다.")
            time.sleep(0.4)
            st.rerun()
        except Exception as exc:
            st.query_params.clear()
            st.error(f"재조회하지 못했습니다: {exc}")


def render_delete_confirmation(df: pd.DataFrame) -> None:
    pending_id = clean_text(st.session_state.get("pending_delete_id", ""))
    if not pending_id or not is_admin():
        return

    matches = df[df["id"].astype(str) == pending_id]
    if matches.empty:
        st.session_state.pop("pending_delete_id", None)
        return
    title = clean_text(matches.iloc[0]["title"])

    st.markdown(
        f'<div class="delete-box">“{html.escape(title)}” 콘텐츠를 삭제할까요?</div>',
        unsafe_allow_html=True,
    )
    yes_col, no_col, _ = st.columns([1, 1, 6])
    with yes_col:
        if st.button("삭제", type="primary", use_container_width=True):
            updated = df[df["id"].astype(str) != pending_id].copy()
            try:
                save_data(updated, f"Delete B tv+ content: {title}")
                st.session_state.pop("pending_delete_id", None)
                st.rerun()
            except Exception as exc:
                st.error(f"삭제하지 못했습니다: {exc}")
    with no_col:
        if st.button("취소", use_container_width=True):
            st.session_state.pop("pending_delete_id", None)
            st.rerun()


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


def render_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.markdown(
            '<div class="empty-box"><b>등록된 콘텐츠가 없습니다.</b><br>'
            '<span style="font-size:12px">상단에서 타이틀을 추가하면 포스터와 OTT 편성 여부가 자동 표시됩니다.</span></div>',
            unsafe_allow_html=True,
        )
        return

    rows: list[str] = []
    for _, row in df.iterrows():
        title = clean_text(row.get("title", ""))
        matched_title = clean_text(row.get("matched_title", ""))
        matched_year = clean_text(row.get("matched_year", ""))
        source_url = clean_text(row.get("source_url", ""))
        open_year = clean_text(row.get("open_year", ""))
        last_checked = clean_text(row.get("last_checked", ""))
        row_id = quote(clean_text(row.get("id", "")))

        details: list[str] = []
        if open_year:
            details.append(open_year)
        if matched_title and normalize_title(matched_title) != normalize_title(title):
            details.append(f"매칭: {matched_title}")
        elif matched_year and matched_year not in details:
            details.append(matched_year)

        source_link = ""
        if source_url:
            source_link = f'<a href="{html.escape(source_url, quote=True)}" target="_blank">근거 보기</a>'
        if last_checked:
            details.append(f"확인 {last_checked}")
        detail_text = " · ".join(html.escape(item) for item in details)
        if source_link:
            detail_text += (" · " if detail_text else "") + source_link

        management = "-"
        if is_admin():
            management = (
                '<div class="action-wrap">'
                f'<a class="icon-button" href="?refresh={row_id}" target="_self" title="다시 확인">↻</a>'
                f'<a class="icon-button" href="?delete={row_id}" target="_self" title="삭제">⌫</a>'
                "</div>"
            )

        rows.append(
            "<tr>"
            f'<td class="title-col"><div class="title-wrap">{poster_html(row)}<div class="title-copy">'
            f'<div class="title-main">{html.escape(title)}</div>'
            f'<div class="title-sub">{detail_text or "-"}</div></div></div></td>'
            f'<td>{html.escape(clean_text(row.get("btv_update_date", "")))}</td>'
            f'<td>{type_badge(clean_text(row.get("content_type", "")))}</td>'
            f'<td class="ott-cell">{ox_badge(row.get("netflix"))}</td>'
            f'<td class="ott-cell">{ox_badge(row.get("coupang"))}</td>'
            f'<td class="ott-cell">{ox_badge(row.get("tving"))}</td>'
            f'<td class="ott-cell">{ox_badge(row.get("wavve"))}</td>'
            f'<td class="ott-cell">{ox_badge(row.get("disney"))}</td>'
            f'<td class="ott-cell">{ox_badge(row.get("watcha"))}</td>'
            f'<td>{management}</td>'
            "</tr>"
        )

    table = (
        '<div class="table-shell"><table class="comparison-table">'
        '<colgroup>'
        '<col style="width:390px"><col style="width:140px"><col style="width:110px">'
        '<col style="width:112px"><col style="width:112px"><col style="width:112px">'
        '<col style="width:112px"><col style="width:128px"><col style="width:112px">'
        '<col style="width:90px">'
        '</colgroup>'
        '<thead><tr>'
        '<th style="text-align:left">포스터 · 타이틀명</th>'
        '<th>B tv+ 업데이트일</th>'
        '<th>콘텐츠 구분</th>'
        '<th><div class="provider-head"><span class="provider-n">N</span><span>넷플릭스</span></div></th>'
        '<th><div class="provider-head"><span class="provider-c">▶</span><span>쿠팡플레이</span></div></th>'
        '<th><div class="provider-head"><span class="provider-t">T</span><span>티빙</span></div></th>'
        '<th><div class="provider-head"><span class="provider-w">W</span><span>웨이브</span></div></th>'
        '<th><div class="provider-head"><span class="provider-d">Disney</span><span>디즈니+</span></div></th>'
        '<th><div class="provider-head"><span class="provider-wa">W</span><span>왓챠</span></div></th>'
        '<th>관리</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
    )
    st.markdown(table, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
render_admin_login()
df = load_data()
handle_query_actions(df)

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

intro_col, guide_col, csv_col = st.columns([6, 1.1, 1.25], vertical_alignment="center")
with intro_col:
    st.markdown(
        """
<div class="intro">
  <div class="intro-title">🎬 B tv+ 업데이트 콘텐츠 OTT 편성 현황</div>
  <div class="intro-sub">B tv+에 업데이트되는 콘텐츠가 주요 OTT에 편성되어 있는지 확인할 수 있습니다. <b style="color:#173b9b">v6 · 정확한 작품 선택형</b></div>
</div>
""",
        unsafe_allow_html=True,
    )
with guide_col:
    if st.button("❔ 사용 가이드", use_container_width=True):
        st.session_state.show_guide = not st.session_state.get("show_guide", False)
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

render_delete_confirmation(df)

if is_admin():
    with st.container(border=True):
        st.markdown('<div class="control-title">새 타이틀 검색 및 추가 <span style="color:#173b9b">(작품 선택 필수)</span></div>', unsafe_allow_html=True)
        with st.form("search_content_form", clear_on_submit=False):
            title_col, date_col, type_col, year_col, search_col = st.columns(
                [2.2, 1.15, 1.0, 0.8, 1.05], vertical_alignment="bottom"
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
            with type_col:
                content_type_input = st.selectbox(
                    "콘텐츠 구분",
                    ["드라마", "예능", "영화", "애니", "키즈", "기타"],
                    label_visibility="collapsed",
                )
            with year_col:
                open_year_input = st.text_input(
                    "공개연도",
                    placeholder="연도",
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
            open_year_input = re.sub(r"\D", "", clean_text(open_year_input))[:4]
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
                    "content_type": content_type_input,
                    "open_year": open_year_input,
                }
                if not candidates:
                    st.warning("일치하는 검색 결과가 없습니다. 제목을 더 정확하게 입력해 주세요.")

        candidates = st.session_state.get("content_search_candidates", [])
        if candidates:
            st.markdown(
                '<div style="font-size:13px;font-weight:900;margin:10px 0 4px">검색 결과에서 정확한 작품을 선택하세요</div>',
                unsafe_allow_html=True,
            )
            import json
            meta = st.session_state.get("content_search_meta", {})
            for index, candidate in enumerate(candidates):
                candidate_title = clean_text(candidate.get("title", ""))
                candidate_year = clean_text(candidate.get("year", ""))
                candidate_poster = clean_text(candidate.get("poster_url", ""))
                result_cols = st.columns([0.55, 3.2, 1.0], vertical_alignment="center")
                with result_cols[0]:
                    if candidate_poster:
                        st.image(candidate_poster, width=66)
                with result_cols[1]:
                    st.markdown(f"**{html.escape(candidate_title)}**")
                    st.caption(candidate_year or "연도 정보 없음")
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
                            selected_year = clean_text(meta.get("open_year", "")) or candidate_year
                            new_row = result_to_row(
                                title=candidate_title,
                                update_date=selected_date,
                                content_type=clean_text(meta.get("content_type", "드라마")),
                                open_year=selected_year,
                                result=result,
                            )
                            updated = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                            try:
                                save_data(updated, f"Add B tv+ content: {candidate_title}")
                                st.session_state.pop("content_search_candidates", None)
                                st.session_state.pop("content_search_query", None)
                                st.session_state.pop("content_search_meta", None)
                                st.success(f"'{candidate_title}'을(를) 추가했습니다.")
                                time.sleep(0.4)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"저장하지 못했습니다: {exc}")
else:
    st.caption("추가·재조회·삭제 기능은 관리자 로그인 후 사용할 수 있습니다.")

with st.container(border=True):
    search_col, type_col, storage_col = st.columns([3.3, 1.2, 1.2], vertical_alignment="center")
    with search_col:
        search_text = st.text_input(
            "타이틀 검색",
            placeholder="타이틀 검색",
            label_visibility="collapsed",
        )
    with type_col:
        type_values = ["전체"]
        if not df.empty:
            type_values += sorted(
                value for value in df["content_type"].astype(str).unique().tolist() if value
            )
        type_filter = st.selectbox(
            "구분",
            type_values,
            label_visibility="collapsed",
        )
    with storage_col:
        storage_text = "GitHub 자동 저장" if github_config() else "앱 내 CSV 저장"
        st.caption(storage_text)

view = df.copy()
if not view.empty:
    if search_text:
        query = normalize_title(search_text)
        view = view[view["title"].apply(normalize_title).str.contains(query, na=False)]
    if type_filter != "전체":
        view = view[view["content_type"] == type_filter]
    view["_date"] = pd.to_datetime(view["btv_update_date"], errors="coerce")
    view = view.sort_values(["_date", "title"], ascending=[False, True]).drop(columns=["_date"])

render_table(view)
st.markdown(
    '<div class="footer-note">※ OTT 편성 현황은 키노라이츠 정액제·바로 보기 데이터를 기반으로 합니다. '
    '실제 서비스 편성 변경이나 동명 작품 매칭에 따라 차이가 있을 수 있습니다.</div>',
    unsafe_allow_html=True,
)
