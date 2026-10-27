"""Validate a browser-collected English research snapshot; never publish to X."""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from run_day import profile_env
from storage import atomic_write, writer_lock
from settings import effective_config


def timestamp(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return t


def validate(s, cfg, now):
    if s.get('profile_id') != cfg['profile_id'] or s.get('language') != 'en':
        raise ValueError('Wrong profile or language')
    if re.search(r'[\u0600-\u06ff]', json.dumps(s, ensure_ascii=False)):
        raise ValueError('Research and drafts must be English-only')
    collected = timestamp(s['collected_at'])
    if not now - timedelta(hours=6) <= collected <= now + timedelta(minutes=5):
        raise ValueError('Collection timestamp is stale or in the future')
    allowed = {a['handle'].lower() for a in cfg['accounts']}
    checks = s['source_checks']
    if set(checks) != allowed or any(v not in ('sampled', 'no_recent_posts', 'unavailable', 'not_observed') for v in checks.values()):
        raise ValueError('Every configured source needs an explicit coverage status')
    posts = s['posts']
    if not 1 <= len(posts) <= 100:
        raise ValueError('A successful update needs 1..100 verified source posts')
    urls = set()
    for p in posts:
        m = re.fullmatch(r'https://x\.com/([A-Za-z0-9_]{1,15})/status/([0-9]+)', p['url'])
        if not m or m[1].lower() not in allowed or checks[m[1].lower()] != 'sampled' or p['url'] in urls:
            raise ValueError('Invalid, duplicate or cross-profile source URL')
        urls.add(p['url'])
        if not collected-timedelta(days=cfg.get('research_days',7)) <= timestamp(p['posted_at']) <= collected:
            raise ValueError('Source post is outside the configured research window')
        if not isinstance(p.get('text'), str) or not 1 <= len(p['text']) <= 10000:
            raise ValueError('Missing source text')
        if not isinstance(p.get('summary'), str) or not p['summary'].strip():
            raise ValueError('Missing English analysis')
        for key in ('views', 'likes', 'reposts', 'replies'):
            v = p.get(key)
            if v is not None and (type(v) is not int or not 0 <= v <= 10**12):
                raise ValueError('Unknown metrics must be null, not fabricated')
    drafts = s['drafts']
    count = cfg.get('draft_count',4)
    if len(drafts) != count or len({d['text'] for d in drafts}) != count:
        raise ValueError('Provide exactly '+str(count)+' distinct drafts')
    for d in drafts:
        if not all(isinstance(d.get(k), str) and d[k].strip() for k in ('title', 'text', 'visual')) or len(d['text']) > 280:
            raise ValueError('Invalid draft')
        if d.get('approval_status') != 'pending' or not d.get('source_urls') or not set(d['source_urls']) <= urls:
            raise ValueError('Drafts require known sources and pending human approval')
        # shortcut: new numerical claims are rejected; add audited claim attribution before allowing them.
        if re.search(r'\d', d['text']):
            raise ValueError('Daily drafts cannot introduce numerical claims')
    if not isinstance(s.get('summary'), str) or not s['summary'].strip():
        raise ValueError('Missing daily summary')
    return collected


def apply(slug, snapshot, now=None):
    env = profile_env(slug)
    data_path = Path(env['XVS_DATA'])
    now = now or datetime.now(timezone.utc)
    cfg = effective_config(slug, json.loads(Path(env['XVS_WATCHLIST']).read_text()))
    collected = validate(snapshot, cfg, now)
    with writer_lock(data_path):
        data = json.loads(data_path.read_text())
        old = data.get('daily_research')
        if old == snapshot:
            return 'unchanged'
        if old and timestamp(old['collected_at']) >= collected:
            raise ValueError('Refusing to overwrite newer research')
        day = collected.astimezone(ZoneInfo('Asia/Tehran')).date().isoformat()
        archive = data_path.parent / 'history' / day
        if archive.is_symlink() or (data_path.parent/'history').is_symlink():
            raise ValueError('History must not be a symlink')
        archive.mkdir(parents=True, exist_ok=True)
        stamp = collected.astimezone(timezone.utc).strftime('%H%M%S%f')
        atomic_write(archive / (stamp+'.json'), json.dumps(snapshot, ensure_ascii=False, indent=2))
        data.update(daily_research=snapshot, date=day, updated=snapshot['collected_at'])
        atomic_write(data_path, json.dumps(data, ensure_ascii=False, indent=2))
    return 'updated'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', required=True)
    p.add_argument('input', type=Path)
    args = p.parse_args()
    try:
        if args.input.stat().st_size > 2*1024*1024:
            raise ValueError('Snapshot too large')
        print(args.profile + ': ' + apply(args.profile, json.loads(args.input.read_text())))
    except (ValueError, KeyError, TypeError, OSError) as e:
        raise SystemExit('Snapshot rejected: '+str(e))
