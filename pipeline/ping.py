#!/usr/bin/env python3
"""Build the daily ping from board/data.json -> digests/<D>/PING.txt (send it verbatim; never recompute by hand).

  ping.py <D> [--board-url https://<you>.github.io/<repo>/]

Format (lang en):
  X digest DD.MM: N hits >=5k (S ★)[ (self-quotes: X)]; +K outsiders.
  X keywords 24h: top-5 kw1 12.3K up, kw2 ...
  Experiment: <posts so far, trend vs non-trend median x-base, or 'sample too small'>
  Board: <your board URL>
Format (lang ru):
  X digest за DD.MM: N хитов ≥5k (S ★)[ (из них самоцитат: X)]; +K outsiders.
  Ключи X 24ч: top-5 ...
  Эксперимент: ...
The self-quote part is omitted when 0. +K excludes trend-input-only accounts.
"""
from __future__ import annotations
from storage import atomic_write

import sys

from common import board_posts, day_dir, load_config, load_data, thresholds

ARROW = {"up": "↑", "down": "↓", "flat": "→", "new": "new"}


def k(n):
    n = int(n or 0)
    return f"{n/1e6:.1f}M" if n >= 1e6 else f"{n/1e3:.1f}K" if n >= 1e3 else str(n)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    D = sys.argv[1]
    cfg = load_config()
    ru = str(cfg.get("lang") or "en").lower() == "ru"
    lo, star = thresholds(cfg)
    d = load_data()
    if d.get("date") != D:
        sys.exit(f"data.json date {d.get('date')} != {D}")
    url = (sys.argv[sys.argv.index("--board-url") + 1] if "--board-url" in sys.argv else
           cfg.get("board_url") or d.get("board_url") or "")
    rows = board_posts(d, cfg)
    hits = [r for lane, r in rows if lane == "watchlist" and int(r.get("views") or 0) >= lo]
    outs = [r for lane, r in rows if lane == "outsider"]
    stars = sum(1 for r in hits if int(r.get("views") or 0) >= star or r.get("highlight") is True)
    sq = sum(1 for r in hits if r.get("self_quote"))
    dd = f"{D[8:10]}.{D[5:7]}"
    floor = f"{lo // 1000}k" if lo % 1000 == 0 else str(lo)
    if ru:
        line1 = (f"X digest за {dd}: {len(hits)} хитов ≥{floor} ({stars} ★)" + (f" (из них самоцитат: {sq})" if sq else "")
                 + f"; +{len(outs)} outsiders.")
    else:
        line1 = (f"X digest {dd}: {len(hits)} hits ≥{floor} ({stars} ★)" + (f" (self-quotes: {sq})" if sq else "")
                 + f"; +{len(outs)} outsiders.")
    lines = [line1]
    xk = ((d.get("trend_radar") or {}).get("x_keywords") or {}).get("keywords") or []
    if xk:
        top = ", ".join(f"{r['keyword']} {k(r['w24']['total'])} {ARROW.get(r.get('trend'), r.get('trend') or '')}".strip()
                        for r in xk[:5])
        lines.append(("Ключи X 24ч (выборка): top-5 " if ru else "X keywords 24h (sample): top-5 ") + top)
    t10 = ((d.get("trend_radar") or {}).get("summary") or {}).get("top10_line")
    if t10:
        lines.append(t10)
    e = d.get("experiment")
    if e:
        T = e.get("totals") or {}
        tr, nt = T.get("trend") or {}, T.get("nontrend") or {}
        n = len(e.get("posts") or [])
        if ru:
            body = (f"постов {n}; тренд n={tr.get('n', 0)} {tr.get('median_x') or '-'}x vs не тренд n={nt.get('n', 0)} "
                    f"{nt.get('median_x') or '-'}x" + (" · выборка мала" if T.get("small_sample") else
                                                     f" · {T.get('lift_pct'):+d}%" if T.get("lift_pct") is not None else ""))
            lines.append(f"Эксперимент {e.get('handle')} {e.get('start')}..{e.get('end')}: {body}")
        else:
            body = (f"{n} posts; trend n={tr.get('n', 0)} {tr.get('median_x') or '-'}x vs non-trend n={nt.get('n', 0)} "
                    f"{nt.get('median_x') or '-'}x" + (" · sample too small" if T.get("small_sample") else
                                                     f" · {T.get('lift_pct'):+d}%" if T.get("lift_pct") is not None else ""))
            lines.append(f"Experiment {e.get('handle')} {e.get('start')}..{e.get('end')}: {body}")
    if url:
        lines.append(("Борд: " if ru else "Board: ") + url)
    text = "\n".join(lines)
    out = day_dir(D)
    out.mkdir(parents=True, exist_ok=True)
    atomic_write((out / "PING.txt"), text + "\n")
    print(text)


if __name__ == "__main__":
    main()
