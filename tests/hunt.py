"""Key rotation, scoring, card validation and page escaping for the trend hunt."""
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import io
import json
from pathlib import Path
import sys
import urllib.error
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'pipeline'))
import hunt as h

now = datetime.now(timezone.utc).replace(microsecond=0)  # createdAt has second precision
calls = []
def fetch(url, headers):
    calls.append(headers['X-API-Key'])
    if headers['X-API-Key'] == 'a':
        raise urllib.error.HTTPError(url, 429, 'limit', {}, io.BytesIO())
    return {'tweets': []}
xs = h.XSearch([{'name': 'a', 'key': 'a'}, {'name': 'b', 'key': 'b'}], fetch, sleep=lambda s: None)
xs.search('q'); xs.search('q')
assert calls == ['a', 'a', 'b', 'b'] and xs.dead == {'a'} and xs.used == {'b': 2} and xs.billed == 2
try:
    h.XSearch([{'name': 'a', 'key': 'a'}], fetch, sleep=lambda s: None).search('q')
    raise AssertionError('exhausted providers accepted')
except h.AllProvidersFailed:
    pass

ring = {'weight': 1}
t = {'createdAt': format_datetime(now-timedelta(hours=2)), 'viewCount': 20000, 'author': {'followers': 1000}}
s = h.score_tweet(t, ring, now)
assert s['velocity'] == 10000 and s['outperformance'] == 20
assert h.score_tweet(dict(t, viewCount=None), ring, now) is None
small = h.score_tweet(dict(t, author={'followers': 100000}), ring, now)
assert small['score'] < s['score'], 'outperformance must reward small accounts'

xposts = [{'url': 'https://x.com/a/status/1', 'text': 'Proxy pool grew to 40 regions'}]
card = dict(kind='quote', urgency='now', ring='core', topic='t', why_hot='w', angle='a', visual='', source_urls=['https://x.com/a/status/1'])
ok, rejected = h.validate_cards([dict(card, text='Pools in 40 regions still fail on soft blocks.'),
                       dict(card, text='We cut failures by 73%.'),
                       dict(card, text='x', source_urls=['https://evil.example/1']),
                       dict(card, text='y'*281)], xposts, [])
assert len(ok) == 1 and ok[0]['approval_status'] == 'pending' and len(rejected) == 3 and 'number not in sources: 73' in rejected[0]
ok2, _ = h.validate_cards([dict(card, text='HTTP 200 is not proof of valid data.')], xposts, [], 'Diagnose soft blocks: HTTP 200 does not guarantee valid data.')
assert len(ok2) == 1, 'brand-config numbers must be allowed'
assert h.clean_hashtags(['webscraping', '#WebScraping', '#bad tag', '#1x', '#AI', '#data', '#extra'], 'text') == ['#webscraping', '#AI', '#data']
assert h.clean_hashtags(['#proxy'], 'Use a #proxy') == [] and h.clean_hashtags('x', 't') == [] and h.clean_hashtags(['#webscraping'], 'y'*270) == []
assert h.trending_hashtags([{'text': 'a #AI b #ai', 'views': 5}, {'text': '#Scraping', 'views': 9}]) == ['#scraping', '#ai']
ok3, _ = h.validate_cards([dict(card, text='Soft blocks matter.', hashtags=['#webscraping', 'no good'])], xposts, [])
assert ok3[0]['hashtags'] == ['#webscraping']
assert 'url=https%3A%2F%2Fx.com%2Fa%2Fstatus%2F1' in h.compose_url(ok[0])
assert 'in_reply_to=1' in h.compose_url(dict(ok[0], kind='reply'))

import os, tempfile
from unittest.mock import patch
with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XVS_SETTINGS_ROOT=tmp, INSIGHT_AI_URL='https://ai.test', INSIGHT_AI_KEY='k'):
    sent = {}
    def post(url, payload, key):
        sent.update(url=url, payload=payload)
        return json.dumps({'choices': [{'message': {'content': '```json\n{"cards": [1]}\n```'}}]})
    xp = [dict(xposts[0], ring='core', author='a', followers=1, views=1, likes=1, reposts=0, hours=1, velocity=1, outperformance=1)]
    assert h.generate({'cards': 3}, {'ai_model': 'm', 'name': 'brand'}, xp, [], post) == ([1], 0)
    assert sent['url'] == 'https://ai.test/v1/chat/completions' and json.loads(sent['payload']['messages'][1]['content'])['N'] == 3

page = h.render({'x': '</script><script>alert(1)</script>'})
assert '</script><script>alert' not in page and json.loads(page.split('id="data">')[1].split('</script>')[0])['x'].startswith('</script>')
print('hunt ok')
