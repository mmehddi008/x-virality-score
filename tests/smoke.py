"""Offline smoke test and harmless reproductions against the pinned upstream code."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'pipeline'))
import drafts

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))

with tempfile.TemporaryDirectory(prefix='xvs-review-') as temp:
    root = Path(temp)
    day = '2026-10-25'
    data = json.loads((REPO / 'board/data.example.json').read_text())
    data.update(date=day, timezone='Asia/Tehran', brand_title='OFFLINE DEMO - synthetic data')
    data['hits'] = [dict(id=str(i), handle=f'@fixture_{i}', views=6000*i,
                        url=f'https://x.com/fixture_{i}/status/{i}',
                        text='AI agents assist developers with repetitive maintenance tasks while humans review every result.',
                        posted_at='2026-10-25T10:00:00Z') for i in (1, 2)]
    cfg = json.loads((REPO / 'config/watchlist.example.json').read_text())
    cfg.update(accounts=[], trend_input_only=[], board_url='', timezone='Asia/Tehran')
    cfg['x_keywords'] = {'core': ['AI agents'], 'max': 1}
    write(root / 'data.json', data)
    write(root / 'config.json', cfg)
    env = dict(os.environ, XVS_DATA=str(root/'data.json'), XVS_WATCHLIST=str(root/'config.json'),
               XVS_DIGEST_ROOT=str(root/'digests'), XVS_LEDGER=str(root/'ledger.json'), PYTHONDONTWRITEBYTECODE='1')
    def run(*args):
        p = subprocess.run(args, cwd=REPO, env=env, text=True, capture_output=True)
        assert p.returncode == 0, (args, p.stdout, p.stderr)
        return p.stdout
    run('bash', 'pipeline/run_day.sh', 'prepare', day)
    parts = root/'digests'/day/'_parts'
    tk = json.loads((parts/'trend_keywords.json').read_text())
    tk['extra'] = ['AI agents']
    write(parts/'trend_keywords.json', tk)
    write(parts/'drafts_v4.json', {str(i): {'draft_en': 'Repetitive upkeep gets a helping hand from AI agents; a developer remains responsible for checking the output.', 'keywords_used': ['AI agents']} for i in (1,2)})
    xdir = root/'digests'/day/'_xkw'
    req = json.loads((xdir/'request.json').read_text())
    for call in req['calls']:
        write(xdir/call['file'], {'data':[{'id':'3','author_id':'9','text':'AI agents sample','public_metrics':{'impression_count':9000}}], 'includes':{'users':[{'id':'9','username':'fixture_3'}]}})
    write(parts/'radar_inputs.json', {
        'ideas':[dict(title=f'Synthetic idea {i}', hook_en='AI agents and human review', angle='AI agents maintenance workflow', topic='AI agents', keywords=['AI agents'], format='video', why='Synthetic test only', visual_type='video', visual='Show a review screen') for i in range(5)],
        'articles':[dict(title=f'Synthetic article {i}', thesis='AI agents with review', outline=['Scope','Review','Results'], keywords=['AI agents'], visual='Workflow diagram', why='Synthetic test only') for i in range(2)]})
    run('bash','pipeline/run_day.sh',day)
    assert (root/'digests'/day/'PING.txt').exists()
    result=json.loads((root/'data.json').read_text())
    assert len(result['drafts_top10']) == 2 and len(result['trend_radar']['ideas']) == 5
    print('PASS: complete synthetic prepare/draft-check/apply/keyword-ingest/radar/ping loop')
    write(root/'digests'/day/'composed.json', {'hits':data['hits']})
    run(sys.executable, 'board/enrich_leaderboards.py', '--as-of', day)
    first=json.loads((root/'ledger.json').read_text())
    run(sys.executable, 'board/enrich_leaderboards.py', '--as-of', day)
    assert first == json.loads((root/'ledger.json').read_text())
    print('PASS: leaderboard repeated run is idempotent')
    # Harmless injection: only prints a marker; no file write or network operation.
    arg = "2026-10-25')); print('XVS_INJECTION_CONFIRMED'); #"
    p=subprocess.run(['bash','pipeline/run_day.sh',arg],cwd=REPO,env=env,text=True,capture_output=True)
    assert 'XVS_INJECTION_CONFIRMED' not in p.stderr and p.returncode != 0
    print('PASS: malicious date rejected without code execution')
    for call in req['calls']:
        write(xdir/call['file'], {'errors':[{'title':'Rate limit exceeded'}]})
    previous=(xdir/'keywords.json').read_bytes()
    failed=subprocess.run([sys.executable,'pipeline/xkw.py','ingest',day],cwd=REPO,env=env,text=True,capture_output=True)
    assert failed.returncode != 0 and (xdir/'keywords.json').read_bytes() == previous
    print('PASS: API errors fail closed and preserve previous results')
    _, errors=drafts.check_one({'draft_en':'AI agents cut costs by 9%.','keywords_used':['AI agents']}, 'AI agents assist developers with repetitive maintenance tasks while humans review every result.', {'ai agents'})
    assert any("numbers not in original" in e for e in errors)
    print('PASS: invented 9% claim rejected')
    import run_day
    for slug in ('../o2co', 'o2co/../bitoff'):
        try: run_day.profile_env(slug)
        except ValueError: pass
        else: raise AssertionError('profile traversal accepted')
    print('PASS: profile traversal rejected')
