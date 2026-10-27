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
    with patch.object(s,'collect',return_value=(posts,{'source':'sampled'})), patch.object(s,'generate',side_effect=OSError('provider unavailable')):
        try: s.run('one');raise AssertionError('AI failure replaced by template')
        except OSError: pass
    assert data.read_bytes()==original
    result={'summary':'Sample only.', 'analyses':{posts[0]['url']:'Practical engineering topic.'},
            'drafts':[{'title':v,'text':v+' useful advice.','visual':'A diagram.',
                       'source_urls':[posts[0]['url']],'approval_status':'approved'} for v in ('First','Second','Third','Fourth')]}
    promotion=copy.deepcopy(result);promotion['drafts'][0]['text']='Choose source for your next project.'
    with patch.object(s,'collect',return_value=(posts,{'source':'sampled'})), patch.object(s,'generate',return_value=promotion):
        try: s.run('one');raise AssertionError('Competitor promotion accepted')
        except ValueError: pass
    assert data.read_bytes()==original
    with patch.object(s,'collect',return_value=(posts,{'source':'sampled'})), patch.object(s,'generate',return_value=result):
        s.run('one')
    saved=json.loads(data.read_text())['daily_research']
    assert all(d['approval_status']=='pending' for d in saved['drafts'])
    with patch.object(s,'collect',side_effect=AssertionError('Duplicate collection')): s.run('one')
    old=json.loads(data.read_text());old['daily_research']['generation_method']='editorial_fallback';data.write_text(json.dumps(old))
    before=data.read_bytes()
    with patch.object(s,'collect',return_value=(posts,{'source':'sampled'})), patch.object(s,'generate',side_effect=OSError('offline')) as model:
        try: s.run('one');raise AssertionError('Template result blocked AI retry')
        except OSError: pass
        assert model.call_count==1 and data.read_bytes()==before
print('PASS: source filtering, unknown metrics, last-good preservation, pending approval and daily idempotency')

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    for slug in ('o2co','bitoff'):
        (root/slug).mkdir(); (root/slug/'config.json').write_text(json.dumps({'accounts':[{'handle':'source'}]}))
    output=root/'capture.json'
    output.write_text('{"old":"must not reuse"}')
    with patch.object(sys,'argv',['fetch_public.py',tmp,str(output)]), patch('urllib.request.OpenerDirector.open',side_effect=OSError('offline')), patch('time.sleep'):
        runpy.run_path(str(Path(__file__).resolve().parents[1]/'pipeline/fetch_public.py'),run_name='__main__')
    assert json.loads(output.read_text())['pages']=={'source':None}
    with patch.dict(os.environ,XVS_TIMELINES_FILE=str(output)), patch('time.sleep'):
        try: s.collect({'profile_id':'o2co','accounts':[{'handle':'source'}]},datetime.now(timezone.utc));raise AssertionError('Empty capture accepted')
        except ValueError: pass
print('PASS: safe capture failures and source sufficiency')

# A rate-limited source is retried once after the requested wait, never in a tight loop.
import io
from urllib.error import HTTPError
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    for slug in ('o2co','bitoff'):
        (root/slug).mkdir();(root/slug/'config.json').write_text(json.dumps({'accounts':[{'handle':'source'}]}))
    responses=[HTTPError('https://syndication.twitter.com',429,'limited',{'Retry-After':'45'},None),io.BytesIO(b'fresh'),io.BytesIO(b'fresh')]
    with patch.object(sys,'argv',['fetch_public.py',tmp,str(root/'capture.json')]), patch('urllib.request.OpenerDirector.open',side_effect=responses) as fetch, patch('time.sleep') as sleep:
        runpy.run_path(str(Path(__file__).resolve().parents[1]/'pipeline/fetch_public.py'),run_name='__main__')
        assert fetch.call_count==3
        sleep.assert_any_call(45)
    assert json.loads((root/'capture.json').read_text())['pages']['source']=='fresh'
print('PASS: source rate limits use a bounded delayed retry')
