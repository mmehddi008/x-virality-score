"""Fetch public embeds with the host's standard Python; no cookies or account session."""
import json
import re
from pathlib import Path
import sys
import time
import urllib.request
from datetime import datetime, timezone
from storage import atomic_write

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

root = Path(sys.argv[1])
output = Path(sys.argv[2])
pages = {}
for slug in ('o2co', 'bitoff'):
    cfg = json.loads((root/slug/'config.json').read_text())
    for account in cfg['accounts']:
        handle = account['handle']
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}', handle):
            raise ValueError('Invalid handle')
        try:
            url = 'https://syndication.twitter.com/srv/timeline-profile/screen-name/'+handle
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.build_opener(NoRedirect).open(req, timeout=25) as response:
                raw = response.read(4*1024*1024+1)
            if len(raw)>4*1024*1024: raise ValueError('Response too large')
            pages[handle.lower()] = raw.decode('utf-8')
        except Exception as exc:
            pages[handle.lower()] = None
            print(handle+': unavailable ('+type(exc).__name__+')', flush=True)
        time.sleep(3)
atomic_write(output,json.dumps({'collected_at':datetime.now(timezone.utc).isoformat(),'pages':pages}))
