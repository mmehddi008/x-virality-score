"""Profile isolation and competing-writer checks, no network."""
import json
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from run_day import profile_env
from storage import writer_lock
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    os.environ['XVS_PROFILE_ROOT'] = temp
    for slug in ('one', 'two'):
        home = root / slug
        home.mkdir()
        for leaf in ('config.json', 'data.json'):
            (home / leaf).write_text(json.dumps({'profile_id': slug}))
    one, two = profile_env('one'), profile_env('two')
    assert set(one.values()).isdisjoint(two.values())
    with writer_lock(one['XVS_DATA']):
        with writer_lock(two['XVS_DATA']):
            pass
        try:
            with writer_lock(one['XVS_DATA']):
                raise AssertionError('same profile accepted competing writer')
        except SystemExit:
            pass
    (root/'two'/'data.json').write_text('{"profile_id":"one"}')
    try:
        profile_env('two')
        raise AssertionError('cross-profile data accepted')
    except ValueError:
        pass
print('PASS: independent profile paths, cross-profile identity rejection and writer exclusion')
