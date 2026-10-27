"""Public sampling excludes stale/foreign posts; invalid generation preserves data."""
import copy
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import runpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'pipeline'))
import server_daily as s
now = datetime.now(timezone.utc)
tweet = dict(id_str='1234567890123456789', created_at=format_datetime(now-timedelta(hours=1)),
             full_text='Useful engineering evidence.', lang='en', user={'screen_name':'source'}, favorite_count=3)
def html(tweets):
    return '<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':{'timeline':{'entries':[
        {'content':{'tweet':t}} for t in tweets]}}}})+'</script>'
bad = []
for changes in ({'user':{'screen_name':'foreign'}}, {'retweeted_status':{'id':'x'}},
                {'in_reply_to_status_id_str':'1'}, {'lang':'fa'},
                {'created_at':format_datetime(now-timedelta(days=8))}):
    t=copy.deepcopy(tweet); t.update(changes); bad.append(t)
posts=s.parse_timeline(html([tweet,tweet]+bad),'source',now)
assert len(posts)==1 and posts[0]['views'] is None and posts[0]['likes']==3
assert posts[0]['url'].endswith(tweet['id_str'])
try:
    s.parse_timeline(html([]),'source',now)
    raise AssertionError('Empty timeline treated as evidence')
except ValueError: pass
with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XVS_PROFILE_ROOT=tmp):
    home=Path(tmp)/'one';home.mkdir()
    (home/'config.json').write_text(json.dumps({'profile_id':'one','accounts':[{'handle':'source'}]}))
    data=home/'data.json';data.write_text('{"profile_id":"one"}')
    original=data.read_bytes()
    with patch.object(s,'collect',return_value=(posts,{'source':'sampled'})), patch.object(s,'generate',return_value={}):
        try: s.run('one');raise AssertionError('Invalid generation accepted')
        except ValueError: pass
    assert data.read_bytes()==original
    result={'summary':'Sample only.', 'analyses':{posts[0]['url']:'Practical engineering topic.'},
            'drafts':[{'title':v,'text':v+' useful advice.','visual':'A diagram.',
                       'source_urls':[posts[0]['url']],'approval_status':'approved'} for v in ('First','Second','Third','Fourth')]}
    with patch.object(s,'collect',return_value=(posts,{'source':'sampled'})), patch.object(s,'generate',return_value=result):
        s.run('one')
    saved=json.loads(data.read_text())['daily_research']
    assert all(d['approval_status']=='pending' for d in saved['drafts'])
    with patch.object(s,'collect',side_effect=AssertionError('Duplicate collection')): s.run('one')
print('PASS: source filtering, unknown metrics, last-good preservation, pending approval and daily idempotency')

from editorial_fallback import prepare
from daily_snapshot import validate
for slug, evidence in [('o2co','Fresh web data for an agent and proxy infrastructure.'), ('bitoff','Gift card shopping with crypto.')]:
    sample=copy.deepcopy(posts); sample[0]['text']=evidence
    result=prepare(slug,sample,[])
    snap=dict(profile_id=slug,language='en',collected_at=now.isoformat(),source_checks={'source':'sampled'},
              summary=result['summary'],posts=[dict(p,summary=result['analyses'][p['url']]) for p in sample],
              drafts=[dict(d,approval_status='pending') for d in result['drafts']])
    validate(snap,{'profile_id':slug,'accounts':[{'handle':'source'}]},now)
    previous=[d['text'] for d in result['drafts']]
    assert not set(previous)&{d['text'] for d in prepare(slug,sample,previous)['drafts']}
try:
    prepare('o2co',[dict(posts[0],text='Unrelated football news.')],[])
    raise AssertionError('Unrelated sources accepted')
except ValueError: pass

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    for slug in ('o2co','bitoff'):
        (root/slug).mkdir(); (root/slug/'config.json').write_text(json.dumps({'accounts':[{'handle':'source'}]}))
    output=root/'capture.json'
    output.write_text('{"old":"must not reuse"}')
    with patch.object(sys,'argv',['fetch_public.py',tmp,str(output)]), patch('urllib.request.urlopen',side_effect=OSError('offline')), patch('time.sleep'):
        runpy.run_path(str(Path(__file__).resolve().parents[1]/'pipeline/fetch_public.py'),run_name='__main__')
    assert json.loads(output.read_text())['pages']=={'source':None}
    with patch.dict(os.environ,XVS_TIMELINES_FILE=str(output)), patch('time.sleep'):
        try: s.collect({'profile_id':'o2co','accounts':[{'handle':'source'}]},datetime.now(timezone.utc));raise AssertionError('Empty capture accepted')
        except ValueError: pass
print('PASS: labelled relevant fallback, next-day variety, safe capture failures and source sufficiency')
