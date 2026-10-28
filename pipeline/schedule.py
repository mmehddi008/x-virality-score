"""Host-side gate for the hourly timers: is a profile's hunt or research due in this Tehran hour?

Hours come from settings/<slug>-automation.json (edited in the panel); without it each runs once a day.
Runs with the host's Python 3.6, so stdlib only and no zoneinfo.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_HOURS = {'hunt': [10], 'research': [9]}
TEHRAN = timedelta(hours=3, minutes=30)  # Iran dropped DST in 2022


def automation(settings, slug):
    path = Path(settings)/(slug+'-automation.json')
    try:
        if path.is_file() and not path.is_symlink():
            data = json.loads(path.read_text())
            if isinstance(data, dict) and data.get('profile_id') == slug:
                return data
    except (OSError, ValueError):
        pass
    return {}


def hours(settings, slug, kind):
    v = (automation(settings, slug).get('schedule') or {}).get(kind+'_hours')
    if not isinstance(v, list):
        return DEFAULT_HOURS[kind]
    return [h for h in v if type(h) is int and 0 <= h < 24]


def due(root, slug, kind, now_utc):
    root = Path(root)
    if kind == 'hunt' and not automation(root/'settings', slug).get('hunt') and not (root/'profiles'/slug/'hunt.json').is_file():
        return False
    return (now_utc+TEHRAN).hour in hours(root/'settings', slug, kind)


if __name__ == '__main__':
    kind, slug = sys.argv[1], sys.argv[2]
    if kind not in DEFAULT_HOURS:
        sys.exit(2)
    sys.exit(0 if due(Path(__file__).resolve().parents[1], slug, kind, datetime.utcnow()) else 1)
