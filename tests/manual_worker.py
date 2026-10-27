import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from manual_worker import consume
with tempfile.TemporaryDirectory() as folder, patch('manual_worker.os.chown'):
    root=Path(folder);(root/'settings').mkdir()
    def put(slug,status):
        (root/'settings'/(slug+'-run.json')).write_text(json.dumps({'profile_id':slug,'status':status}))
    def get(slug):return json.loads((root/'settings'/(slug+'-run.json')).read_text())
    put('o2co','queued');put('bitoff','idle');calls=[]
    consume(root,lambda slug:calls.append(slug))
    assert calls==['o2co'] and get('o2co')['status']=='ok' and get('bitoff')['status']=='idle'
    consume(root,lambda slug:calls.append(slug));assert calls==['o2co']
    put('bitoff','queued')
    def fail(slug):raise RuntimeError('private provider error')
    consume(root,fail)
    assert get('bitoff')['status']=='failed' and 'private' not in get('bitoff')['error']
    put('o2co','running');consume(root,fail)
    assert get('o2co')['status']=='failed' and 'interrupted' in get('o2co')['error']
print('PASS queue isolation, one execution, safe failure and interrupted recovery')
