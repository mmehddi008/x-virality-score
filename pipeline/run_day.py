"""Run one day transactionally; --profile isolates all configuration and output."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def profile_env(slug):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', slug):
        raise ValueError('Invalid profile ID')
    root = Path(os.environ.get('XVS_PROFILE_ROOT', HERE.parent / 'profiles')).resolve()
    home = (root / slug).resolve()
    if home.parent != root or not home.is_dir():
        raise ValueError('Unknown profile')
    for leaf in ('config.json', 'data.json', 'ledger.json', 'digests'):
        if (home / leaf).is_symlink():
            raise ValueError('Profile files must not be symlinks')
    cfg = json.loads((home / 'config.json').read_text())
    data = json.loads((home / 'data.json').read_text())
    if cfg.get('profile_id') != slug or data.get('profile_id') != slug:
        raise ValueError('Profile identity mismatch')
    return dict(XVS_DATA=str(home/'data.json'), XVS_WATCHLIST=str(home/'config.json'),
                XVS_LEDGER=str(home/'ledger.json'), XVS_DIGEST_ROOT=str(home/'digests'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile')
    parser.add_argument('mode_or_date')
    parser.add_argument('date', nargs='?')
    parser.add_argument('--skip-drafts', action='store_true')
    args = parser.parse_args()
    if args.profile:
        os.environ.update(profile_env(args.profile))
    from common import DATA, day_dir, load_config, load_data
    from storage import atomic_write, writer_lock
    prepare = args.mode_or_date == 'prepare'
    day = args.date if prepare else args.mode_or_date
    if not day or (not prepare and args.date):
        parser.error('Use [--profile SLUG] prepare YYYY-MM-DD or YYYY-MM-DD')
    folder = day_dir(day)
    cfg = load_config()
    if load_data().get('date') != day:
        raise ValueError('Board date must match the requested day')
    with writer_lock(DATA), tempfile.TemporaryDirectory(prefix='.run-', dir=DATA.parent) as temp:
        staged = Path(temp) / 'data.json'
        staged.write_bytes(DATA.read_bytes())
        env = dict(os.environ, XVS_DATA=str(staged))
        def run(script, *params):
            subprocess.run([sys.executable, str(HERE/script), *params], env=env, check=True)
        run('trend_input.py', day)
        if prepare:
            run('drafts.py', 'keywords', day)
            run('xkw.py', 'request', day)
            if (cfg.get('experiment') or {}).get('enabled'):
                run('experiment.py', 'request', day)
            run('drafts.py', 'top10', day)
        else:
            if not args.skip_drafts:
                run('drafts.py', 'check', day)
                run('xkw.py', 'ingest', day)
                run('drafts.py', 'apply', day)
            run('radar.py', 'build', day, *(['--no-ideas-ok'] if args.skip_drafts else []))
            if (cfg.get('experiment') or {}).get('enabled'):
                run('experiment.py', 'build', day)
            d = json.loads(staged.read_text())
            d['collection_status'] = 'partial' if args.skip_drafts else 'ready'
            d['drafts_skipped'] = args.skip_drafts
            atomic_write(staged, json.dumps(d, ensure_ascii=False, indent=2))
            run('ping.py', day)
        atomic_write(DATA, staged.read_text())
    print(f'Completed {"prepare" if prepare else "run"}: {args.profile or "default"} / {day}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
