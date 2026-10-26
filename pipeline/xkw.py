#!/usr/bin/env python3
"""X keyword table: views across all of X, last 24 h vs the previous 24 h (sampled via read-only search).

  xkw.py request <D> [--n 16]  -> digests/<D>/_xkw/request.json  (keywords + exact search args + call budget)
  xkw.py ingest  <D>           -> digests/<D>/_xkw/keywords.json (ranked table; radar.py embeds it in data.json)

The agent runs every call in request.json with the read-only x MCP tool `search_posts_all` and saves the
RAW output as digests/<D>/_xkw/<call.file>. Two calls per keyword: last 24 h and previous 24 h
(24-48 h ago), sort_order=relevancy, max_results=25, lang:en, no retweets / replies.

IMPORTANT: each window is a SAMPLE of up to 25 top-relevance posts (API max per call), not every post on X.
Numbers = impression_count of the sampled posts at fetch time. The board labels the table as a sample.

Candidates (config/watchlist.json "x_keywords"):
  "core": [...]              fixed niche list (~16), checked every day
  "query_override": {kw: q}  disambiguation for short / ambiguous terms
  "max": 16                  keywords per run (2 calls each -> 32 reads)
plus the top trend keywords of D (drafts.py keywords) and optional digests/<D>/_xkw/candidates_extra.json.
"""
from __future__ import annotations
from storage import atomic_write

import json
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone

from common import day_dir, load_config, api_posts

DEFAULT_CORE = ["AI agents", "Claude Code", "ChatGPT", "OpenAI", "Anthropic", "Gemini", "Grok", "MCP", "Codex",
                "vibe coding", "open source", "prompt injection", "AI video", "LLM", "Cursor", "second brain"]
TAIL = " lang:en -is:retweet -is:reply"


def slug(k):
    return re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_")


def request(D: str, n: int | None = None):
    cfg = load_config().get("x_keywords") or {}
    n = n or int(cfg.get("max") or 16)
    override = cfg.get("query_override") or {}
    day = day_dir(D)
    out = day / "_xkw"
    out.mkdir(parents=True, exist_ok=True)
    kws = list(cfg.get("core") or DEFAULT_CORE)
    low = lambda: {x.lower() for x in kws}
    tk = day / "_parts" / "trend_keywords.json"
    if tk.exists():
        for r in json.loads(tk.read_text())["keywords"][:15]:
            k = r["keyword"]
            if len(k) > 3 and k.lower() not in low() and (any(c.isupper() for c in k) or " " in k):
                kws.append(k)
    ex = out / "candidates_extra.json"
    if ex.exists():
        kws += [k for k in json.loads(ex.read_text()) if k.lower() not in low()]
    kws = kws[:n]
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    fmt = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    start, mid = fmt(now - timedelta(hours=48)), fmt(now - timedelta(hours=24))
    calls = []
    for k in kws:
        for w, st, en in (("24h", mid, None), ("prev24h", start, mid)):
            a = {"query": override.get(k, f'"{k}"') + TAIL, "start_time": st, "max_results": 25,
                 "sort_order": "relevancy", "post.fields": "public_metrics,created_at,author_id",
                 "expansions": "author_id", "user.fields": "username"}
            if en:
                a["end_time"] = en
            calls.append({"keyword": k, "window": w, "file": f"{slug(k)}__{w}.json", "tool": "search_posts_all", "args": a})
    req = {"date": D, "created": now.isoformat(), "window_start": start, "budget_calls": len(calls),
           "pace": "stay under the x MCP rate limits (e.g. <=25 calls/min); 25 posts max per call", "calls": calls}
    atomic_write((out / "request.json"), json.dumps(req, ensure_ascii=False, indent=2))
    print(f"{len(calls)} search calls -> {out / 'request.json'}")


def agg(lst):
    if not lst:
        return {"n": 0, "total": 0, "median": 0, "top": None}
    top = max(lst, key=lambda x: x["views"])
    return {"n": len(lst), "total": sum(x["views"] for x in lst), "median": int(statistics.median(x["views"] for x in lst)),
            "top": top}


def ingest(D: str):
    out = day_dir(D) / "_xkw"
    req = json.loads((out / "request.json").read_text())
    kws = []
    for c in req["calls"]:
        if c["keyword"] not in kws:
            kws.append(c["keyword"])
    rows = []
    for k in kws:
        b, miss, query = {}, False, ""
        for c in [c for c in req["calls"] if c["keyword"] == k]:
            query = c["args"]["query"]
            f = out / c["file"]
            if not f.exists():
                raise ValueError(f"Missing search response: {f.name}")
            d, posts = api_posts(f)
            users = {u["id"]: u.get("username") for u in (d.get("includes") or {}).get("users") or []}
            lst = []
            for p in posts:
                v = int((p.get("public_metrics") or {}).get("impression_count") or 0)
                h = users.get(p.get("author_id")) or "i"
                lst.append({"views": v, "url": f"https://x.com/{h}/status/{p['id']}", "handle": "@" + h,
                            "text": re.sub(r"\s+", " ", p.get("text", ""))[:120]})
            b[c["window"]] = lst
        if miss and not b:
            rows.append({"keyword": k, "missing": True})
            continue
        a24, ap = agg(b.get("24h", [])), agg(b.get("prev24h", []))
        ratio = (a24["total"] / ap["total"]) if ap["total"] else None
        trend = ("up" if ratio >= 1.3 else "down" if ratio <= 0.7 else "flat") if ratio is not None else \
            ("new" if a24["n"] else "-")
        tops = [t for t in (a24["top"], ap["top"]) if t]
        rows.append({"keyword": k, "query": query, "w24": a24, "prev24": ap,
                     "w48": {"n": a24["n"] + ap["n"], "total": a24["total"] + ap["total"],
                             "top": max(tops, key=lambda x: x["views"]) if tops else None},
                     "change": round(ratio, 2) if ratio is not None else None, "trend": trend, "partial": miss,
                     "top_share": round(a24["top"]["views"] / a24["total"], 2) if a24["total"] else None})
    ok = [r for r in rows if not r.get("missing")]
    ok.sort(key=lambda r: -r["w24"]["total"])
    for i, r in enumerate(ok, 1):
        r["rank"] = i
    res = {"date": D, "fetched_at": req["created"], "window_start": req["window_start"], "calls": len(req["calls"]),
           "sample": True, "sample_size_per_call": 25,
           "method": ("Read-only x MCP search_posts_all, 2 calls per keyword: last 24 h and previous 24 h (24-48 h ago); "
                      "lang:en, no retweets/replies, sort=relevancy, up to 25 posts per window. This is a SAMPLE of "
                      "top-relevance posts, not every post on X. Views = impression_count at fetch time. Rank = sum of "
                      "sampled 24 h views; 48 h = both windows; trend = 24 h sum / previous 24 h sum (up >=1.3, down <=0.7). "
                      "Fresh posts are still gaining views, so 'up' is understated. Top-post share > 70% means one viral "
                      "post carries the keyword."),
           "keywords": ok, "missing": [r["keyword"] for r in rows if r.get("missing")]}
    atomic_write((out / "keywords.json"), json.dumps(res, ensure_ascii=False, indent=2))
    for r in ok:
        print(f"{r['rank']:>2} {r['keyword']:<20} 24h n={r['w24']['n']:>3} total={r['w24']['total']:>11,} | "
              f"prev total={r['prev24']['total']:>11,} | {r['trend']} x{r['change']}")
    if res["missing"]:
        print("missing:", res["missing"])


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if sys.argv[1] == "request":
        request(sys.argv[2], int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else None)
    elif sys.argv[1] == "ingest":
        ingest(sys.argv[2])
    else:
        sys.exit(__doc__)
