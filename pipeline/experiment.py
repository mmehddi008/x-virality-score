#!/usr/bin/env python3
"""Experiment tracker: trend vs non-trend posts of the operator, inside a time window.

  experiment.py request <D>  -> digests/<D>/_exp/request.json : ONE read-only x MCP call (get_users_posts) for the
                                operator timeline (baseline window + experiment window). Save RAW output as
                                digests/<D>/_exp/timeline.json; if meta.next_token -> same call + pagination_token
                                -> timeline__p2.json, __p3 ...
  experiment.py build <D>    -> board/data.json["experiment"] (+ history in digests/_experiment.json)

Config (config/watchlist.json "experiment"):
  enabled          true to run
  handle, user_id  operator handle (no @) and numeric X user id (get_users_by_usernames once)
  start, end       experiment window, YYYY-MM-DD (inclusive, operator timezone from "timezone")
  baseline_days    pre-window days used for the baseline median (default 30)
  trend_threshold  trend label at >= this trend match % (default 35)
  min_n            "sample too small" until each group has n >= this (default 5)
  min_age_h        totals use only posts at least this old (default 24; younger posts still gain views)
  hypothesis       free text shown on the board, e.g. "trend posts get about +50% vs non-trend"

Rules:
- Posts = operator originals in the window (no replies / reposts). Self-quotes COUNT (self-quote badge only).
- Baseline = median views of operator originals posted in the baseline_days before start (n shown), overall and
  per media type. x_base = views / baseline median.
- trend_match (strict): only keywords KNOWN BEFORE the post = the trend_keywords.json of the latest daily run
  created before posted_at (keyword used by another author, not only the operator, and specific: a phrase, name,
  acronym or versioned name; generic single words like 'agent', 'model', 'video' do not count) plus that run's X
  keyword table. Score = 1 - prod(1 - w(rank)), w = .35 (top-10) / .22 (11-25) / .12. Label trend at >= threshold.
- The fair comparison is inside one format: video vs video, image vs image, text vs text.
"""
from __future__ import annotations
from storage import atomic_write

import glob
import json
import math
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import ROOT, canon, clean, day_dir, labels, load_config, load_data, load_raw, save_data

try:
    from zoneinfo import ZoneInfo
except Exception:   # pragma: no cover
    ZoneInfo = None

GENERIC = {"pro", "max", "plus", "ultra", "api", "ai", "app", "apps", "video", "model", "agent", "free", "new", "open",
           "code", "dev", "tool", "tools", "bot", "bots", "repo", "github", "x", "thread", "update", "launch"}
STORE = ROOT / "_experiment.json"


def cfg_exp():
    cfg = load_config()
    e = dict(cfg.get("experiment") or {})
    if not e.get("enabled"):
        sys.exit("experiment disabled (config/watchlist.json experiment.enabled=false) - nothing to do")
    for k in ("handle", "user_id", "start", "end"):
        if not e.get(k):
            sys.exit(f"experiment.{k} missing in config/watchlist.json")
    try:
        tz = ZoneInfo(cfg.get("timezone") or "UTC")
    except Exception:
        tz = timezone.utc
    e["tz"] = tz
    e["t0"] = datetime.fromisoformat(e["start"] + "T00:00:00").replace(tzinfo=tz)
    e["t1"] = datetime.fromisoformat(e["end"] + "T23:59:59").replace(tzinfo=tz)
    e["b0"] = e["t0"] - timedelta(days=int(e.get("baseline_days") or 30))
    return cfg, e


def z(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def request(D):
    _, e = cfg_exp()
    args = {"id": str(e["user_id"]), "start_time": z(e["b0"]), "exclude": "replies,retweets", "max_results": 25,
            "post.fields": "public_metrics,created_at,author_id,attachments,referenced_tweets,note_tweet,text",
            "expansions": "attachments.media_keys,referenced_tweets.id,referenced_tweets.id.author_id",
            "media.fields": "type,duration_ms"}
    if datetime.now(timezone.utc) > e["t1"]:
        args["end_time"] = z(e["t1"])
    out = day_dir(D) / "_exp"
    out.mkdir(parents=True, exist_ok=True)
    req = {"tool": "get_users_posts", "args": args,
           "save_as": f"{out}/timeline.json (raw; meta.next_token -> same call + pagination_token -> timeline__p2.json)",
           "budget": "1 read (+1 per extra page)"}
    atomic_write((out / "request.json"), json.dumps(req, ensure_ascii=False, indent=2))
    print(json.dumps(req, ensure_ascii=False, indent=2))


def specific(key, lab):
    if " " in key:
        return True
    if key in GENERIC:
        return False
    return bool(re.search(r"\d", lab)) or (lab[:1].isupper() and len(lab) > 2)


def weight(r):
    return 0.35 if r <= 10 else 0.22 if r <= 25 else 0.12


_RUNS = None


def runs():
    """[(created_utc, day, keywords[(key, rank, others:set, label)])] for every digest day with trend_keywords.json"""
    global _RUNS
    if _RUNS is not None:
        return _RUNS
    out = []
    for p in sorted(glob.glob(str(ROOT / "*" / "_parts" / "trend_keywords.json"))):
        tk = json.loads(Path(p).read_text())
        created = tk.get("created")
        if not created:
            continue
        D = Path(p).parent.parent.name
        rows = [(r["key"], r["rank"], set(r.get("author_handles") or []), r["keyword"]) for r in tk["keywords"]]
        xk = Path(p).parent.parent / "_xkw" / "keywords.json"
        if xk.exists():
            have = {k for k, *_ in rows}
            for r in json.loads(xk.read_text()).get("keywords", []):
                k = " ".join(w.lower() for w in r["keyword"].split())
                if k not in have:
                    rows.append((k, r["rank"], {"x-search"}, r["keyword"]))
        out.append((datetime.fromisoformat(created.replace("Z", "+00:00")), D, rows))
    out.sort()
    _RUNS = out
    return out


def trend_match(text, posted_at, me):
    known = [r for r in runs() if r[0] < posted_at]
    if not known:
        return 0, [], None
    _, D, kws = known[-1]
    low = " " + " ".join(re.findall(r"[a-z0-9][a-z0-9.+#'\-]*", text.lower())) + " "
    hit = []
    for k, r, auth, lab in kws:
        if not (auth - {me}) or not specific(k, lab):
            continue
        norm = " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in k.split())
        if (f" {k} " in low or f" {k}s " in low) and norm not in {h[3] for h in hit}:
            hit.append((k, r, lab, norm))
    hit = [h for h in hit if not any(o[0] != h[0] and f" {h[0]} " in f" {o[0]} " for o in hit)]
    sc = 1 - math.prod(1 - weight(h[1]) for h in hit) if hit else 0.0
    return round(100 * sc), [h[2] for h in sorted(hit, key=lambda h: h[1])], D


def med(v):
    return round(statistics.median(v), 2) if v else None


def build(D):
    cfg, e = cfg_exp()
    L = labels(cfg)
    me = canon(e["handle"])
    uid = str(e["user_id"])
    thr = int(e.get("trend_threshold") or 35)
    min_n = int(e.get("min_n") or 5)
    min_age = int(e.get("min_age_h") or 24)
    hit_views = int(e.get("hit_views") or cfg.get("min_views") or 5000)
    store = json.loads(STORE.read_text()) if STORE.exists() else {"posts": {}}
    for f in sorted(glob.glob(str(ROOT / "*" / "_exp" / "timeline*.json")), key=lambda f: Path(f).stat().st_mtime):
        d = load_raw(f)
        inc = d.get("includes") or {}
        media = {m["media_key"]: m.get("type") for m in inc.get("media") or []}
        qauth = {t["id"]: t.get("author_id") for t in inc.get("tweets") or []}
        fetched = datetime.fromtimestamp(Path(f).stat().st_mtime, timezone.utc).isoformat(timespec="minutes")
        for p in d.get("data") or []:
            refs = {r["type"]: r["id"] for r in p.get("referenced_tweets") or []}
            if "replied_to" in refs or "retweeted" in refs:
                continue
            t = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00"))
            types = {media.get(k) for k in (p.get("attachments") or {}).get("media_keys") or []}
            mt = "video" if types & {"video", "animated_gif"} else "image" if "photo" in types else "text"
            rec = store["posts"].setdefault(p["id"], {"id": p["id"], "url": f"https://x.com/{me}/status/{p['id']}",
                                                      "posted_at": t.isoformat(), "views_history": {}})
            rec.update({"text": clean((p.get("note_tweet") or {}).get("text") or p.get("text") or "")[:280], "media": mt,
                        "self_quote": bool("quoted" in refs and str(qauth.get(refs["quoted"])) == uid)})
            rec["views_history"][fetched] = int((p.get("public_metrics") or {}).get("impression_count") or 0)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(STORE, json.dumps(store, ensure_ascii=False, indent=1))
    now = datetime.now(timezone.utc)
    base, base_media, rows = [], {}, []
    for rec in store["posts"].values():
        t = datetime.fromisoformat(rec["posted_at"])
        hist = rec["views_history"]
        views = hist[max(hist)] if hist else 0
        if e["b0"] <= t < e["t0"]:
            base.append(views)
            base_media.setdefault(rec.get("media") or "text", []).append(views)
        elif e["t0"] <= t <= e["t1"]:
            rows.append((rec, t, views))
    bmed = statistics.median(base) if base else None
    posts = []
    for rec, t, views in sorted(rows, key=lambda x: x[1]):
        tm, kws, kD = trend_match(rec.get("text", ""), t, me)
        age_h = round((now - t).total_seconds() / 3600, 1)
        posts.append({"id": rec["id"], "url": rec["url"], "posted_at": rec["posted_at"],
                      "date": t.astimezone(e["tz"]).strftime("%d.%m %H:%M"), "text": rec.get("text", "")[:280],
                      "media": rec.get("media") or L["no_data"], "self_quote": rec.get("self_quote", False),
                      "views": views, "x_base": round(views / bmed, 2) if bmed else None,
                      "trend_match": tm, "matched_keywords": kws[:8], "keywords_from_run": kD,
                      "label": L["trend"] if tm >= thr else L["nontrend"], "age_h": age_h, "mature": age_h >= min_age})

    def grp(lst):
        xs = [r["x_base"] for r in lst if r["x_base"] is not None]
        return {"n": len(lst), "median_x": med(xs),
                "hit_rate": round(100 * sum(r["views"] >= hit_views for r in lst) / len(lst)) if lst else None,
                "median_views": round(statistics.median([r["views"] for r in lst])) if lst else None}
    mat = [r for r in posts if r["mature"]]
    T = [r for r in mat if r["label"] == L["trend"]]
    N = [r for r in mat if r["label"] != L["trend"]]
    by_media = {}
    for m in ("video", "image", "text"):
        t_, n_ = [r for r in T if r["media"] == m], [r for r in N if r["media"] == m]
        if t_ or n_:
            g1, g2 = grp(t_), grp(n_)
            lift = round(100 * (g1["median_x"] / g2["median_x"] - 1)) if g1["median_x"] and g2["median_x"] else None
            by_media[m] = {"trend": g1, "nontrend": g2, "lift_pct": lift, "comparable": bool(t_ and n_),
                           "baseline_median": round(statistics.median(base_media[m])) if base_media.get(m) else None}
    gT, gN = grp(T), grp(N)
    lift = round(100 * (gT["median_x"] / gN["median_x"] - 1)) if gT["median_x"] and gN["median_x"] else None
    small = gT["n"] < min_n or gN["n"] < min_n
    if not posts:
        verdict = "No posts in the experiment window yet - the next daily run picks them up."
    elif small:
        verdict = (f"Sample too small (trend {gT['n']}, non-trend {gN['n']}; need >= {min_n} each) - no conclusion yet."
                   + (f" Preliminary: trend {gT['median_x']}x vs non-trend {gN['median_x']}x ({lift:+d}%)." if lift is not None else ""))
    else:
        verdict = f"Trend {gT['median_x']}x vs non-trend {gN['median_x']}x of baseline ({lift:+d}%)."
    d = load_data()
    d["experiment"] = {
        "title": "Experiment: trend vs non-trend", "handle": "@" + me, "start": e["start"], "end": e["end"],
        "updated": now.isoformat(timespec="minutes"), "content_day": D,
        "baseline": {"median": round(bmed) if bmed else None, "n": len(base),
                     "window": f"{e['b0'].date()} .. {e['t0'].date()} (before start)",
                     "by_media": {m: round(statistics.median(v)) for m, v in base_media.items()}},
        "threshold": thr, "hit": hit_views, "min_n": min_n, "min_age_h": min_age, "posts": posts,
        "totals": {"trend": gT, "nontrend": gN, "lift_pct": lift, "small_sample": small, "by_media": by_media,
                   "fresh_excluded": len(posts) - len(mat)},
        "hypothesis": e.get("hypothesis") or "", "verdict": verdict, "labels": L,
        "method": (f"trend_match (strict): keywords known before the post (trend list of the last daily run created "
                   f"before posted_at + that run's X keyword table), used by another author and specific; label trend at "
                   f">= {thr}%. x_base = views / median of the operator's originals in the {e.get('baseline_days') or 30} "
                   f"days before start. Totals use posts older than {min_age} h; compare inside one media type."),
    }
    save_data(d)
    print(f"experiment: posts={len(posts)} mature={len(mat)} baseline median={d['experiment']['baseline']['median']} "
          f"n={len(base)} | {verdict}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("request", "build"):
        sys.exit(__doc__)
    {"request": request, "build": build}[sys.argv[1]](sys.argv[2])
