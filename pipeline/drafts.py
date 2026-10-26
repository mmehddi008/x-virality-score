#!/usr/bin/env python3
"""Draft rules v4 helper: trend keywords, TOP-10 originals, overlap gate, apply to data.json.

Drafts are WRITTEN BY THE AGENT during the daily run - this script never writes prose. It:
  drafts.py keywords <D>    -> digests/<D>/_parts/trend_keywords.json  (ranked last-24h keywords, top 40)
  drafts.py top10 <D>       -> digests/<D>/_parts/originals.json       (the 10 most-viewed board posts; alias: originals)
  drafts.py check <D>       reads digests/<D>/_parts/drafts_v4.json, prints per-draft stats, exit 1 on any reject
  drafts.py apply <D>       runs check first (refuses on reject), then patches board/data.json
                            (draft_en, draft_keywords, draft_check, top10_rank, original_en, board_rank,
                            drafts_top10[], trend_keywords{})

Drafts exist ONLY for the TOP-10 most-viewed board posts (watchlist hits + outsiders together, minus
trend-input-only accounts; self-quotes count). Every other card shows the original text and no draft.
drafts_v4.json: {"<post id>": {"draft_en": "...", "keywords_used": ["...", ...]}, ...}

Keyword sources (local JSON only): data.json hits / virals / outsiders / trend_input_only_posts /
last24h.posts, raw last-24h timelines in digests/<D>/_24h/*.json, and the day's pattern brief
(data.json patterns / keyword_brief). Optional curation in trend_keywords.json survives re-runs:
"extra": [names the ranker missed], "exclude": [noise].
"""
from __future__ import annotations
from storage import atomic_write

import glob
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from common import (BANNED_DASHES, board_posts, canon, clean, day_dir, load_config, load_data, load_raw,
                    post_id, record_text, save_data, thresholds)

MAX_4GRAM = 0.30      # share of draft word 4-grams that also occur in the original (reject above)
MAX_WORD = 0.75       # share of draft content-word types also in the original (reject above)
MAX_RUN = 7           # longest run of consecutive words copied from the original (reject at or above)
MIN_KW = 1            # hard floor of trend keywords per draft (target 3-6 where they fit the meaning)
TOP_N = 10
AI_TELLS = ["game-changer", "game changer", "delve", "unlock the", "in today's fast-paced", "here's the thing",
            "revolutionize", "seamlessly", "elevate your", "let's dive in", "dive into", "in the ever-evolving",
            "testament to"]

STOP = set("""a about above after again against all am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers him his how
i if in into is it its itself just me more most my no nor not now of off on once only or other our out over own same she
should so some such than that the their them then there these they this those through to too under until up very was we
were what when where which while who whom why will with you your yours yourself im i'm it's its dont don't thats that's
one two get got go going like make makes made every new also even still really here's heres let lets via vs per back
much many way thing things people anyone everyone someone nobody something everything nothing day days week time now
just today tonight yesterday ago first last next right left big best own use used using u ur yes yeah ok okay
would could should might may must shall can't cant won't wont didn't didnt isn't isnt aren't arent wasn't wasnt
""".split())
GENERIC = set("""insane unreal crazy gold treasure save bookmark follow below thread post posts
course full guide step steps prompt prompts setup setups link links reply replies comment comments check paste free
says said told tell know see look want need try start stop keep run runs running work works working build builds
built ship ships shipped shipping drop drops dropped open opens opened close closed watch watched find found give gives
just here thing whole entire actually literally honestly seriously completely""".split())
# Niche words that count as keywords even in lowercase. Extend per niche with
# "keyword_domain_terms": [...] in config/watchlist.json.
DOMAIN_DEFAULT = set("""agent agents agentic skills skill memory repo repos open-source automation workflow workflows bot bots
security vulnerability scanner dashboard notes loop sandbox benchmark model models local inference pricing plugin
plugins startup founder video videos stack voice""".split())

WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+#/'\-]*[A-Za-z0-9+#]|[A-Za-z0-9]")
NUM = re.compile(r"\$?\d+(?:[.,]\d+)*(?:%|[kmxb]\b)?", re.I)
CAPS: dict[str, tuple[int, int]] = {}


def toks(t: str) -> list[str]:
    return [w.lower().strip(".'") for w in WORD.findall(t.replace("\u2019", "'"))]


def ngrams(ws, n):
    return [tuple(ws[i:i + n]) for i in range(len(ws) - n + 1)]


def norm_key(key: str) -> str:
    return " ".join(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w for w in key.split())


# ---------------------------------------------------------------- sources
def h24_posts(day: Path, floor: int) -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(day / "_24h" / "*.json"))):
        d = load_raw(f)
        key = Path(f).stem.split("__")[0]
        for p in d.get("data") or []:
            v = int((p.get("public_metrics") or {}).get("impression_count") or 0)
            if v >= floor:
                t = (p.get("note_tweet") or {}).get("text") or p.get("text") or ""
                out.append({"id": p["id"], "handle": "@" + key, "views": v, "text": clean(t), "src": "24h",
                            "posted_at": p.get("created_at")})
    return out


def data_posts(d: dict, floor: int) -> list[dict]:
    out = []
    lanes = (("hit", d.get("hits") or []), ("hit", d.get("excluded_hits") or []),
             ("outsider", (d.get("virals") or d.get("outsiders") or [])),
             ("trend_input", d.get("trend_input_only_posts") or []),
             ("24h", (d.get("last24h") or {}).get("posts") or []))
    for src, lst in lanes:
        for r in lst:
            v = int(r.get("views") or 0)
            if src == "24h" and v < floor:
                continue
            out.append({"id": post_id(r), "handle": r.get("handle"), "views": v, "text": record_text(r), "src": src,
                        "posted_at": r.get("posted_at")})
    return [p for p in out if p["id"]]


def brief_terms(d: dict) -> list[str]:
    terms = list(d.get("patterns") or [])
    b = d.get("keyword_brief") or d.get("watchlist_brief") or {}
    if isinstance(b, dict):
        terms += b.get("phrases") or []
        for r in b.get("recurring_names") or []:
            terms.append(re.split(r"\s*\(", r)[0])
    return [str(t) for t in terms]


# ---------------------------------------------------------------- keywords
def learn_case(texts):
    CAPS.clear()
    for t in texts:
        for sent in re.split(r"(?<=[.!?:\n])\s*|\n", t):
            ws = [w.strip(".'") for w in WORD.findall(sent.replace("\u2019", "'"))]
            for i, w in enumerate(ws):
                if not w or not w[0].isalpha():
                    continue
                c, l = CAPS.get(w.lower(), (0, 0))
                if w[0].isupper() and i > 0 and not w.isupper():
                    c += 1
                elif w[0].islower():
                    l += 1
                CAPS[w.lower()] = (c, l)


def entityish(label: str) -> bool:
    if re.search(r"\d", label) or "." in label.strip("."):
        return True
    w = label.lower()
    if w in STOP or w in GENERIC:
        return False
    if label.isupper() and 2 <= len(label) <= 5:
        return True
    c, l = CAPS.get(w, (0, 0))
    return label[:1].isupper() and c >= 1 and c >= l


def candidates(text: str, domain: set[str]):
    text = re.sub(r"\S*\*\S*", " ", text)
    raw = [w.strip(".'") for w in WORD.findall(text.replace("\u2019", "'"))]
    low = [w.lower() for w in raw]
    found = {}
    for n in (1, 2, 3):
        for i in range(len(low) - n + 1):
            g = low[i:i + n]
            if g[0] in STOP or g[-1] in STOP or g[0] in GENERIC or g[-1] in GENERIC:
                continue
            if n == 3 and g[1] in STOP:
                continue
            if n == 1 and (len(g[0]) < 3 or g[0].isdigit()):
                continue
            if n == 1 and not entityish(raw[i]) and g[0] not in domain:
                continue
            if n > 1 and not (any(entityish(x) for x in raw[i:i + n]) or any(x in domain for x in g)):
                continue
            if all(re.fullmatch(r"[\d.,$%kmx]+", w) for w in g) or (n > 1 and re.fullmatch(r"\d+", g[0])):
                continue
            found.setdefault(norm_key(" ".join(g)), " ".join(raw[i:i + n]))
    return found


def rank_keywords(D: str, top: int = 40) -> dict:
    cfg = load_config()
    floor, _ = thresholds(cfg)
    domain = DOMAIN_DEFAULT | {w.lower() for w in cfg.get("keyword_domain_terms") or []}
    day = day_dir(D)
    d = load_data()
    posts = {}
    for p in data_posts(d, floor) + h24_posts(day, floor):
        posts.setdefault(p["id"], p)
    learn_case([p["text"] for p in posts.values()])
    stats = defaultdict(lambda: {"score": 0.0, "posts": set(), "authors": set(), "srcs": set(), "label": {}})
    for p in posts.values():
        w = math.log10(max(p["views"], 1000))
        for key, lab in candidates(p["text"], domain).items():
            s = stats[key]
            s["score"] += w
            s["posts"].add(p["id"]); s["authors"].add(canon(p["handle"])); s["srcs"].add(p["src"])
            s["label"][lab] = s["label"].get(lab, 0) + 1
    bt = brief_terms(d)
    btl = " | ".join(bt).lower()
    tkp = day / "_parts" / "trend_keywords.json"
    old = json.loads(tkp.read_text()) if tkp.exists() else {}
    excl = {norm_key(x.lower()) for x in old.get("exclude", [])}
    rows = []
    for key, s in stats.items():
        if key in excl:
            continue
        na = len(s["authors"])
        inbrief = key in btl
        lab0 = max(s["label"], key=lambda l: s["label"][l])
        if na < 2 and not (inbrief and " " in key) and not (len(s["posts"]) >= 2 and entityish(lab0.split()[0])):
            continue
        n = len(key.split())
        lab = max(s["label"], key=lambda l: (not l.isupper(), s["label"][l]))
        if lab.isupper() and len(lab) > 5:
            lab = lab.title()
        ent = 1.25 if (any(c.isupper() for c in lab) or re.search(r"\d", lab)) else 1.0
        score = s["score"] * (1 + 0.35 * (na - 1)) * (1 + 0.3 * (n - 1)) * ent * (1.3 if inbrief else 1.0)
        rows.append({"keyword": lab, "key": key, "score": round(score, 1), "posts": len(s["posts"]), "authors": na,
                     "author_handles": sorted(s["authors"]), "sources": sorted(s["srcs"]), "in_brief": inbrief})
    rows.sort(key=lambda r: -r["score"])
    drop = set()
    for r in rows:   # prefer the longer phrase when it carries most of a shorter one's support
        for o in rows:
            if r["key"] != o["key"] and f" {r['key']} " in f" {o['key']} " and o["posts"] >= 0.6 * r["posts"]:
                drop.add(r["key"]); break
    kept = [r for r in rows if r["key"] not in drop][:top]
    for i, r in enumerate(kept, 1):
        r["rank"] = i
    return {"date": D, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": "day D board posts + last-24h posts >= min_views + outsiders + trend-input accounts + pattern brief",
            "method": "sum(log10 views) over distinct posts x author spread x phrase length x entity/brief bonus; >=2 authors",
            "n_posts": len(posts), "keywords": kept, "brief_phrases": bt,
            "extra": old.get("extra", []), "exclude": old.get("exclude", [])}


def load_trend(D: str):
    p = day_dir(D) / "_parts" / "trend_keywords.json"
    if not p.exists():
        sys.exit(f"missing {p} - run: drafts.py keywords {D}")
    tk = json.loads(p.read_text())
    keys = {r["keyword"].lower() for r in tk["keywords"]} | {r["key"] for r in tk["keywords"]} | \
        {x.lower() for x in tk.get("extra", [])}
    return tk, keys


# ---------------------------------------------------------------- top-10
def board_top(D: str, n: int = TOP_N) -> list[dict]:
    d = load_data()
    if d.get("date") != D:
        sys.exit(f"data.json is for {d.get('date')}, not {D} - build day D into board/data.json first")
    rows = []
    for lane, r in board_posts(d):
        rows.append({"id": post_id(r), "handle": r.get("handle"), "views": int(r.get("views") or 0), "lane": lane,
                     "text": record_text(r), "url": r.get("url") or r.get("status_url"),
                     "self_quote": bool(r.get("self_quote"))})
    rows.sort(key=lambda r: -r["views"])
    for k, r in enumerate(rows, 1):
        r["rank"] = k
    return rows[:n] if n else rows


def originals(D: str) -> dict:
    o = {r["id"]: r for r in board_top(D)}
    p = day_dir(D) / "_parts"
    p.mkdir(parents=True, exist_ok=True)
    atomic_write((p / "originals.json"), json.dumps(o, ensure_ascii=False, indent=2))
    return o


# ---------------------------------------------------------------- checks
def longest_run(a, b, where=False):
    best, end = 0, 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, end = cur[j], i
        prev = cur
    return (best, " ".join(a[end - best:end])) if where else best


def nums(t):
    return {re.sub(r"[,\s]", "", n.lower()).rstrip(".") for n in NUM.findall(t)}


def overlap(draft: str, orig: str) -> dict:
    d, o = toks(draft), toks(orig)
    g4d, g4o = set(ngrams(d, 4)), set(ngrams(o, 4))
    cw_d = {w for w in d if w not in STOP and len(w) > 2}
    cw_o = {w for w in o if w not in STOP and len(w) > 2}
    run, run_text = longest_run(d, o, True)
    return {"g4": round(len(g4d & g4o) / max(len(g4d), 1), 3), "words": round(len(cw_d & cw_o) / max(len(cw_d), 1), 3),
            "run": run, "run_text": run_text, "len_draft": len(d), "len_orig": len(o)}


def check_one(ent, orig, trend_keys):
    draft = ent.get("draft_en") or ""
    kws = ent.get("keywords_used") or []
    st = overlap(draft, orig)
    errs = []
    if len(draft) > 280:
        errs.append("draft exceeds 280 characters")
    if not draft.strip():
        errs.append("empty draft")
    if st["g4"] > MAX_4GRAM:
        errs.append(f"4-gram overlap {st['g4']:.0%} > {MAX_4GRAM:.0%}")
    if st["words"] > MAX_WORD and st["len_draft"] > 25:
        errs.append(f"content-word overlap {st['words']:.0%} > {MAX_WORD:.0%}")
    if st["run"] >= MAX_RUN:
        errs.append(f"copied run of {st['run']} words: '{st['run_text']}'")
    if any(ch in draft for ch in BANNED_DASHES):
        errs.append("em/en dash present (use '-')")
    low = draft.lower()
    tells = [t for t in AI_TELLS if t in low]
    if tells:
        errs.append(f"AI-sounding phrases: {tells}")
    for k in kws:
        if k.lower() not in low:
            errs.append(f"keyword '{k}' listed but not in draft")
        if k.lower() not in trend_keys:
            errs.append(f"keyword '{k}' not in trend_keywords.json")
    if len(kws) < MIN_KW and st["len_orig"] >= 12:
        errs.append(f"only {len(kws)} trend keywords (min {MIN_KW})")
    allowed = nums(orig)
    extra = sorted(nums(draft) - allowed)
    if extra:
        errs.append(f"numbers not in original: {extra}")
    if re.match(r"\s*(@|replying|great post|this!|so true|agree)", low):
        errs.append("reads like a reply/comment - drafts are standalone posts")
    st["keywords_used"] = kws
    return st, errs


def run_check(D: str, quiet=False):
    _, keys = load_trend(D)
    orig = originals(D)
    dp = day_dir(D) / "_parts" / "drafts_v4.json"
    if not dp.exists():
        print(f"DRAFTS MISSING: {dp} - write drafts per templates/DRAFT_RULES.md (v4)", file=sys.stderr)
        return {}, {"_": ["drafts_v4.json missing"]}
    drafts = json.loads(dp.read_text())
    stats, bad = {}, {}
    for pid, o in orig.items():
        if pid not in drafts:
            bad[pid] = [f"no draft for top-{TOP_N} post #{o['rank']}"]
            continue
        st, errs = check_one(drafts[pid], o["text"], keys)
        stats[pid] = st
        if errs:
            bad[pid] = errs
        if not quiet:
            print(f"{'REJECT' if errs else 'ok':6} {pid} {str(o['handle']):<16} 4g={st['g4']:.0%} words={st['words']:.0%} "
                  f"run={st['run']} kw={len(st['keywords_used'])} {'; '.join(errs)}")
    if not quiet:
        extra = [k for k in drafts if k not in orig]
        if extra:
            print(f"note: {len(extra)} drafts are for posts outside the top-{TOP_N} - ignored")
        if stats:
            g = [s["g4"] for s in stats.values()]
            print(f"SUMMARY drafts={len(stats)} rejected={len(bad)} 4gram mean={sum(g)/len(g):.1%} max={max(g):.1%}")
        elif bad:
            print(f"SUMMARY drafts=0 rejected={len(bad)}")
    return stats, bad


def apply(D: str):
    stats, bad = run_check(D, quiet=True)
    if bad:
        run_check(D)
        sys.exit("drafts rejected - rewrite them (templates/DRAFT_RULES.md, v4) and re-run")
    drafts = json.loads((day_dir(D) / "_parts" / "drafts_v4.json").read_text())
    tk, _ = load_trend(D)
    trend = {"date": D, "window": tk["window"], "method": tk["method"],
             "keywords": [{"keyword": r["keyword"], "rank": r["rank"], "score": r["score"], "posts": r["posts"],
                           "authors": r["authors"]} for r in tk["keywords"]]}
    have = {k["keyword"].lower() for k in trend["keywords"]}
    for x in tk.get("extra", []):
        if x.lower() not in have:
            trend["keywords"].append({"keyword": x, "rank": len(trend["keywords"]) + 1, "curated": True})
    orig = originals(D)
    allsrc = {r["id"]: r for r in board_top(D, 0)}
    d = load_data()
    n = 0
    for key in ("hits", "excluded_hits", "virals", "outsiders"):
        for rec in d.get(key) or []:
            pid = post_id(rec)
            if pid in allsrc:
                rec.setdefault("original_en", allsrc[pid]["text"])
                rec["board_rank"] = allsrc[pid]["rank"]
            if pid in orig and pid in drafts:
                s_ = stats[pid]
                rec["draft_en"] = drafts[pid]["draft_en"]
                rec["draft_keywords"] = drafts[pid].get("keywords_used") or []
                rec["draft_check"] = {"rules": "v4", "g4_overlap": s_["g4"], "word_overlap": s_["words"],
                                      "max_copied_run": s_["run"]}
                rec["top10_rank"] = orig[pid]["rank"]
                n += 1
            else:   # outside the top-10: no draft on the board
                for k in ("draft_en", "draft_keywords", "draft_check", "top10_rank"):
                    rec.pop(k, None)
    d["drafts_top10"] = [{"rank": r["rank"], "id": r["id"], "handle": r["handle"], "views": r["views"], "lane": r["lane"]}
                         for r in orig.values()]
    d["trend_keywords"] = trend
    save_data(d)
    print(f"applied v4 drafts to {n} records (top-{TOP_N} only); trend_keywords={len(trend['keywords'])}")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, D = sys.argv[1], sys.argv[2]
    if cmd == "keywords":
        tk = rank_keywords(D)
        p = day_dir(D) / "_parts"
        p.mkdir(parents=True, exist_ok=True)
        atomic_write((p / "trend_keywords.json"), json.dumps(tk, ensure_ascii=False, indent=2))
        print(f"{len(tk['keywords'])} keywords from {tk['n_posts']} posts -> {p / 'trend_keywords.json'}")
        print(", ".join(f"{r['rank']}.{r['keyword']}" for r in tk["keywords"]))
    elif cmd in ("top10", "originals"):
        o = originals(D)
        print(f"TOP-{TOP_N} posts needing v4 drafts -> {day_dir(D) / '_parts' / 'originals.json'}")
        for r in o.values():
            print(f"  #{r['rank']:<2} {r['views']:>9,} {r['lane']:<9} {str(r['handle']):<16} {r['id']}  {r['text'][:70]!r}")
    elif cmd == "check":
        _, bad = run_check(D)
        sys.exit(1 if bad else 0)
    elif cmd == "apply":
        apply(D)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
