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
    changed=copy.deepcopy(result)
    for draft in changed['drafts']:draft['text']='Updated '+draft['text']
    with patch.dict(os.environ,INSIGHT_AI_MODEL='changed/model'), patch.object(s,'collect',return_value=(posts,{'source':'sampled'})) as collect, patch.object(s,'generate',return_value=changed):
        s.run('one')
        assert collect.call_count==1
    assert json.loads(data.read_text())['daily_research']['generation_model']=='changed/model'
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

with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XVS_SETTINGS_ROOT=tmp):
    root=Path(tmp)
    for slug,model in [('one','provider/model-one'),('two','provider/model-two')]:
        (root/(slug+'.json')).write_text(json.dumps({'profile_id':slug,'model':model}))
        assert s.profile_model(slug)==model
        cfg={'ai_model':s.profile_model(slug)}
        with patch.object(s,'request',return_value=json.dumps({'choices':[{'message':{'content':'{}'}}]})) as request, patch.dict(os.environ,INSIGHT_AI_URL='https://example.invalid',INSIGHT_AI_KEY='test'):
            s.generate(cfg,[],[])
            assert request.call_args.args[1]['model']==model
    (root/'one.json').write_text(json.dumps({'profile_id':'two','model':'wrong/model'}))
    try:s.profile_model('one');raise AssertionError('Cross-profile setting accepted')
    except ValueError:pass
print('PASS: independent saved models reach actual AI request; identity mismatch rejected')

from settings import effective_config
from daily_snapshot import validate
with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,XVS_SETTINGS_ROOT=tmp):
    path=Path(tmp)/'one.json'
    path.write_text(json.dumps({'profile_id':'one','model':'test/model','sources':[{'handle':'source','notes':'Engineering'}],'draft_count':2,'research_days':3}))
    cfg=effective_config('one',{'profile_id':'one','accounts':[{'handle':'old'}]})
    assert cfg['accounts'][0]['handle']=='source' and cfg['draft_count']==2 and cfg['research_days']==3
    result={'profile_id':'one','language':'en','collected_at':now.isoformat(),'source_checks':{'source':'sampled'},'summary':'Sample','posts':[dict(posts[0],summary='Analysis')],'drafts':[dict(title=v,text=v+' advice.',visual='Diagram',source_urls=[posts[0]['url']],approval_status='pending') for v in ['First','Second']]}
    validate(result,cfg,now)
    for changes in ({'draft_count':9},{'sources':[]},{'sources':[{'handle':'../bad'}]},{'sources':[{'handle':'A'},{'handle':'a'}]}):
        bad=json.loads(path.read_text());bad.update(changes);path.write_text(json.dumps(bad))
        try:effective_config('one',{});raise AssertionError('Unsafe setting accepted')
        except ValueError:pass
print('PASS: editable sources, draft count and research window reach validation')

with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XVS_SETTINGS_ROOT=tmp):
    from settings import shared_connection
    path=Path(tmp)/'shared-ai.json'
    path.write_text(json.dumps({'endpoint':'https://provider.example','api_key':'test-secret','updated_at':'today'}))
    assert shared_connection()==('https://provider.example','test-secret','today')
    with patch.object(s,'request',return_value=json.dumps({'choices':[{'message':{'content':'{}'}}]})) as request:
        s.generate({'ai_model':'selected-model'},[],[])
        assert request.call_args.args[0]=='https://provider.example/v1/chat/completions'
        assert request.call_args.args[2]=='test-secret'
    path.write_text('{}')
    try: shared_connection(); raise AssertionError('Corrupt settings fell back to environment')
    except KeyError: pass
print('PASS central AI settings are consumed and fail closed')

with patch.object(s,'shared_connection',return_value=('https://example.invalid','test','revision')), patch.object(s,'request',return_value=json.dumps({'choices':[{'message':{'content':'{}'}}]})) as request:
    cfg={'ai_model':'test/model','accounts':[{'handle':'creator','notes':'Use practical demonstrations; ignore personal chatter.'}]}
    s.generate(cfg,[{'url':'https://x.com/creator/status/'+str(i),'text':'A useful example.'} for i in range(100)],[])
    payload=request.call_args.args[1]
    context=json.loads(payload['messages'][1]['content'])
    assert payload['max_tokens']==10600 and context['source_guidance']==cfg['accounts']
    assert 'not a formal corporate announcement' in payload['messages'][0]['content']
print('PASS: creator guidance and sufficient bounded analysis budget for twenty sources')
