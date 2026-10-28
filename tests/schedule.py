import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'pipeline'))
from schedule import due
from storage import record_usage

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder); (root/'settings').mkdir(); (root/'profiles'/'o2co').mkdir(parents=True)
    at = lambda h, m=0: datetime(2026, 10, 28, h, m)  # UTC; Tehran is +3:30
    assert due(root, 'o2co', 'research', at(5, 30)) and not due(root, 'o2co', 'research', at(6, 30))
    assert not due(root, 'o2co', 'hunt', at(6, 30)), 'no hunt config means no hunt'
    (root/'profiles'/'o2co'/'hunt.json').write_text('{}')
    assert due(root, 'o2co', 'hunt', at(6, 30))
    (root/'settings'/'o2co-automation.json').write_text(json.dumps({'profile_id': 'o2co', 'schedule': {'hunt_hours': [8, 20], 'research_hours': []}}))
    assert due(root, 'o2co', 'hunt', at(16, 45)) and not due(root, 'o2co', 'hunt', at(6, 30))
    assert not any(due(root, 'o2co', 'research', at(h)) for h in range(24)), 'empty list turns research off'
    (root/'settings'/'o2co-automation.json').write_text('{"profile_id":"other","schedule":{"hunt_hours":[]}}')
    assert due(root, 'o2co', 'hunt', at(6, 30)), 'foreign file ignored'
    home = root/'profiles'/'o2co'
    record_usage(home, x_requests=2, ai_tokens=10); record_usage(home, x_requests=1)
    days = json.loads((home/'usage.json').read_text())
    assert days['profile_id'] == 'o2co' and list(days['days'].values()) == [{'x_requests': 3, 'ai_tokens': 10}]
print('schedule ok')
