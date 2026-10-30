"""Non-blocking, process-safe resource slot shared by SMARTINI and ingestion."""
from contextlib import contextmanager
import os
from pathlib import Path


@contextmanager
def slot(root):
    path = Path(root) / '.smartinis-heavy.lock'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os,'O_NOFOLLOW',0), 0o600)
    handle = os.fdopen(fd,'r+b',buffering=0)
    acquired = False
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                if path.stat().st_size == 0:
                    handle.write(b'0')
                handle.seek(0)
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (BlockingIOError, PermissionError, OSError) as exc:
            if isinstance(exc,OSError) and exc.errno not in (11,13,35,36):
                raise
        yield acquired
    finally:
        if acquired:
            if os.name=='nt':
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_UN)
        handle.close()
