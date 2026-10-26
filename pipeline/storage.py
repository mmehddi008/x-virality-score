"""Atomic writes and a shared per-profile writer lock (macOS/Linux)."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import tempfile


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            os.fchmod(f.fileno(), path.stat().st_mode & 0o777 if path.exists() else 0o640)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def writer_lock(data):
    path = Path(data).parent / '.writer.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another writer is running for this profile')
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
