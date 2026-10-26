"""Shared helpers for the X Virality Score pipeline (stdlib only, read-only on X).

Paths (override with env):
  XVS_DIGEST_ROOT  default <repo>/digests          one folder per content day: digests/YYYY-MM-DD/
  XVS_DATA         default <repo>/board/data.json  the board JSON the page reads
  XVS_WATCHLIST    default <repo>/config/watchlist.json

Nothing here talks to X. The agent fetches with the read-only x MCP connector and saves the RAW
tool output as files; these scripts only read local JSON and write local JSON.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import date
from pathlib import Path
from storage import atomic_write

PIPE_DIR = Path(__file__).resolve().parent
REPO_DIR = PIPE_DIR.parent


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else default


ROOT = _env_path("XVS_DIGEST_ROOT", REPO_DIR / "digests")
DATA = _env_path("XVS_DATA", REPO_DIR / "board" / "data.json")
WATCHLIST = _env_path("XVS_WATCHLIST", REPO_DIR / "config" / "watchlist.json")

BANNED_DASHES = ["\u2014", "\u2013", "\u2012", "\u2015"]   # em/en/figure dashes - short hyphen only

# Board / ping labels. Pick with "lang": "en" | "ru" in config/watchlist.json.
LABELS = {
    "en": {"trend": "trend", "visual": "visual", "author": "author/audience", "other": "coincidence/other",
           "nontrend": "non-trend", "self_quote": "self-quote", "no_data": "no data"},
    "ru": {"trend": "тренд", "visual": "визуал", "author": "автор/аудитория", "other": "совпадение/другое",
           "nontrend": "не тренд", "self_quote": "самоцитата", "no_data": "нет данных"},
}


def load_config() -> dict:
    if not WATCHLIST.exists():
        raise SystemExit(f"missing {WATCHLIST}. Copy config/watchlist.example.json to config/watchlist.json first.")
    return json.loads(WATCHLIST.read_text())


def labels(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else load_config()
    return LABELS.get(str(cfg.get("lang") or "en").lower(), LABELS["en"])


def canon(h) -> str:
    return str(h or "").strip().lstrip("@").lower()


def trend_input_only(cfg: dict | None = None) -> set[str]:
    """Accounts used ONLY as trend signals (keyword ranking / radar corpus). Never shown as hits,
    outsiders, leaderboard rows, top-10 drafts or follower tracking."""
    cfg = cfg if cfg is not None else load_config()
    out = set()
    for a in cfg.get("trend_input_only") or []:
        out.add(canon(a.get("handle") if isinstance(a, dict) else a))
    return out


def operator_handle(cfg: dict | None = None, data: dict | None = None) -> str:
    cfg = cfg if cfg is not None else load_config()
    exp = cfg.get("experiment") or {}
    h = (os.environ.get("XVS_OPERATOR_HANDLE") or exp.get("handle") or cfg.get("operator_handle")
         or ((data or {}).get("operator") or {}).get("handle") or (data or {}).get("brand_handle") or "")
    return canon(h)


def thresholds(cfg: dict | None = None) -> tuple[int, int]:
    cfg = cfg if cfg is not None else load_config()
    return int(cfg.get("min_views") or 5000), int(cfg.get("star_views") or 10000)


def day_dir(D: str) -> Path:
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', D):
        raise ValueError('Expected date YYYY-MM-DD')
    date.fromisoformat(D)
    path = ROOT / D
    if path.resolve().parent != ROOT.resolve():
        raise ValueError('Digest path escapes profile')
    return path


def load_data() -> dict:
    if not DATA.exists():
        raise SystemExit(f"missing {DATA}. Copy board/data.example.json to board/data.json and build day D first.")
    return json.loads(DATA.read_text())


def save_data(d: dict) -> None:
    cfg = load_config()
    if cfg.get('profile_id') and d.get('profile_id') != cfg['profile_id']:
        raise ValueError('Profile mismatch')
    d['dashboard_targets'] = dict(cfg.get('dashboard_targets') or {}, minHitViews=thresholds(cfg)[0], starViews=thresholds(cfg)[1])
    atomic_write(DATA, json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def clean(t: str) -> str:
    t = html.unescape(t or "")
    t = re.sub(r"\s*https?://\S+", "", t)
    return t.strip()


def load_raw(path) -> dict:
    """Return the first JSON object in a saved tool output that looks like an X API response."""
    s = open(path, encoding="utf-8").read()
    i = s.find("{")
    dec = json.JSONDecoder()
    while i != -1:
        try:
            obj, _ = dec.raw_decode(s, i)
            if isinstance(obj, dict) and ("data" in obj or "meta" in obj or "errors" in obj):
                return obj
        except Exception:
            pass
        i = s.find("{", i + 1)
    raise ValueError(f'Invalid raw API response: {Path(path).name}')


def api_posts(path):
    obj = load_raw(path)
    if obj.get('errors') or obj.get('error'):
        raise ValueError(f'API error in {Path(path).name}; no metrics published')
    posts = obj.get('data')
    if posts is None and (obj.get('meta') or {}).get('result_count') == 0:
        posts = []
    if not isinstance(posts, list):
        raise ValueError(f'Missing API data in {Path(path).name}')
    for post in posts:
        views = (post.get('public_metrics') or {}).get('impression_count')
        if isinstance(views, bool) or not isinstance(views, int) or views < 0:
            raise ValueError(f'Missing/invalid impression_count in {Path(path).name}')
    return obj, posts


def post_id(r: dict) -> str:
    m = re.search(r"/status/(\d+)", r.get("url") or r.get("status_url") or "")
    return str(r.get("id") or (m.group(1) if m else ""))


def record_text(r: dict) -> str:
    return clean(r.get("original_en") or r.get("full_text") or r.get("text") or r.get("original") or r.get("hook") or "")


def board_posts(d: dict, cfg: dict | None = None) -> list[dict]:
    """Posts shown on the board: watchlist hits + outsiders (virals), minus trend-input-only accounts.
    Self-quotes COUNT (they only carry a badge); same-text duplicates belong in excluded_hits."""
    tio = trend_input_only(cfg)
    rows = []
    for lane, lst in (("watchlist", d.get("hits") or []), ("outsider", d.get("virals") or d.get("outsiders") or [])):
        for r in lst:
            if canon(r.get("handle")) in tio:
                continue
            rows.append((lane, r))
    return rows
