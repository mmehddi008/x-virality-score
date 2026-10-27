"""Fetch public embeds with the host's standard Python; no cookies or account session."""
import json
import re
from pathlib import Path
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from storage import atomic_write
from settings import effective_config

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

root = Path(sys.argv[1])
output = Path(sys.argv[2])
pages = {}
slugs = sys.argv[3:] or ['o2co', 'bitoff']
if any(slug not in ('o2co', 'bitoff') for slug in slugs):
    raise ValueError('Invalid profile')
for slug in slugs:
    try:
        cfg = effective_config(slug, json.loads((root/slug/'config.json').read_text()))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(slug+': settings unavailable ('+type(exc).__name__+')', flush=True)
        continue
    for account in cfg['accounts']:
        handle = account['handle']
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}', handle):
            raise ValueError('Invalid handle')
        try:
            url = 'https://syndication.twitter.com/srv/timeline-profile/screen-name/'+handle
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
            for attempt in range(2):
                try:
                    with urllib.request.build_opener(NoRedirect).open(req, timeout=25) as response:
                        raw = response.read(4*1024*1024+1)
                    break
                except urllib.error.HTTPError as exc:
                    if attempt or exc.code not in (429, 503):
                        raise
                    retry = exc.headers.get('Retry-After', '30')
                    delay = int(retry) if retry.isdigit() else 30
                    if delay > 90:
                        raise
                    time.sleep(max(30, delay))
            if len(raw)>4*1024*1024: raise ValueError('Response too large')
            pages[handle.lower()] = raw.decode('utf-8')
        except Exception as exc:
            pages[handle.lower()] = None
            print(handle+': unavailable ('+type(exc).__name__+')', flush=True)
        time.sleep(3)
atomic_write(output,json.dumps({'collected_at':datetime.now(timezone.utc).isoformat(),'pages':pages}))
