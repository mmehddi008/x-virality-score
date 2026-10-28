"""Fixed-profile private queue consumer; no X write capabilities."""
import json
import os
import subprocess
import signal
from datetime import datetime, timezone
from pathlib import Path
from storage import atomic_write


def consume(root, execute):
    # <slug>-run.json queues daily research, <slug>-hunt-run.json queues a trend hunt.
    for slug, kind in [(slug, kind) for slug in ('o2co', 'bitoff') for kind in ('research', 'hunt')]:
        path = root / 'settings' / (slug + ('-hunt' if kind == 'hunt' else '') + '-run.json')
        if not path.exists() or path.is_symlink() or path.stat().st_size > 4096:
            continue
        try:
            run = json.loads(path.read_text())
            if run['profile_id'] != slug or run['status'] not in ('queued', 'running'):
                continue
        except (ValueError, KeyError, TypeError):
            continue
        def save():
            atomic_write(path, json.dumps(run))
            os.chown(str(path), 10001, 10001)
        if run['status'] == 'running':
            run.update(status='failed', error='Execution was interrupted. Please retry.')
        else:
            run['status'] = 'running'
            save()
            try:
                execute(slug) if kind == 'research' else execute(slug, 'hunt')
                run['status'] = 'ok'
            except Exception:
                run.update(status='failed', error='Research or AI generation failed. Previous drafts remain available. Check the saved model, connection and sources, then retry.')
        run['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()


def execute(slug, kind='research'):
    args = ['hunt', slug] if kind == 'hunt' else [slug]
    process = subprocess.Popen(['/bin/bash', '/opt/insight/twitter/deploy/run-research.sh'] + args, start_new_session=True)
    try:
        if process.wait(timeout=2400):
            raise RuntimeError('Research failed')
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise
    finally:
        name = ('insight-twitter-hunt-' if kind == 'hunt' else 'insight-twitter-manual-') + slug
        subprocess.run(['/usr/bin/docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



if __name__ == '__main__':
    consume(Path('/opt/insight/twitter'), execute)
