"""Daily snapshots reject unsafe/stale input and retain independent last-good data."""
import copy
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from daily_snapshot import apply
now=datetime.now(timezone.utc)
url='https://x.com/source/status/123'
s={'profile_id':'one','language':'en','collected_at':now.isoformat(),'source_checks':{'source':'sampled'},'summary':'A sampled daily update.','posts':[{'url':url,'posted_at':(now-timedelta(hours=1)).isoformat(),'text':'Source evidence.','summary':'An engineering topic.','views':None}], 'drafts':[{'title':t,'text':t+' practical original draft.','visual':'A diagram.','approval_status':'pending','source_urls':[url]} for t in ['First','Second','Third','Fourth']]}
with tempfile.TemporaryDirectory() as tmp:
 os.environ['XVS_PROFILE_ROOT']=tmp
 for slug in ('one','two'):
  home=Path(tmp)/slug;home.mkdir()
  (home/'config.json').write_text(json.dumps({'profile_id':slug,'accounts':[{'handle':'source'}]}))
  (home/'data.json').write_text(json.dumps({'profile_id':slug,'marker':slug}))
 other=(Path(tmp)/'two/data.json').read_bytes()
 assert apply('one',s,now)=='updated'
 assert apply('one',s,now)=='unchanged'
 before=(Path(tmp)/'one/data.json').read_bytes()
 mutations=[lambda v:v.update(profile_id='two'),lambda v:v.update(language='fa'),lambda v:v.update(summary='فارسی'),lambda v:v.update(collected_at=(now-timedelta(days=1)).isoformat()),lambda v:v.update(posts=[]),lambda v:v['drafts'][0].update(approval_status='approved'),lambda v:v['drafts'][0].update(text='Guaranteed 99% uptime'),lambda v:v['posts'][0].update(url='https://x.com/other/status/123'),lambda v:v['posts'][0].update(views=-1),lambda v:v.update(source_checks={})]
 for mutate in mutations:
  bad=copy.deepcopy(s);mutate(bad)
  try:apply('one',bad,now);raise AssertionError('Invalid update accepted')
  except ValueError:pass
  assert (Path(tmp)/'one/data.json').read_bytes()==before
 assert (Path(tmp)/'two/data.json').read_bytes()==other
 assert len(list((Path(tmp)/'one/history').glob('*/*.json')))==1
print('PASS: English-only, pending approval, source attribution, freshness, idempotency, history and last-good profile isolation')
