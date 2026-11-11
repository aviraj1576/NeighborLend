from contextlib import contextmanager

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError

LOCK_PATH = EP_ROOT / ".runtime" / "cv-worker.lock"


@contextmanager
def worker_guard():
    """One native worker/recovery operation across all local EP data directories.

    Windows releases the byte-range lock when a process exits, including crashes.
    A persisted lock file alone does not indicate that a worker is still alive.
    """
    import msvcrt

    path = LOCK_PATH
    if path.is_symlink() or not path.resolve().is_relative_to(EP_ROOT):
        raise EPError(409, "artifact_path", "Unsafe worker lock path")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise EPError(409, "worker_busy", "Another native CV worker is active") from exc
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
