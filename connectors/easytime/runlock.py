"""Single-instance run lock for the connector.

Task Scheduler has a "do not start a new instance" setting, and it is not
enough on its own: it does not cover a manual `run_sync.ps1` typed by an
operator while the scheduled run is mid-flight, it does not cover a second
scheduled task someone adds later, and it is a checkbox that can be
unticked. Two concurrent runs would fetch the same window and race on the
cursor - harmless for the punch data (Postgres deduplicates) but perfectly
capable of writing a cursor backwards.

**How the lock works, and why it is this and not a PID file.**

The obvious design - write the PID to a file and have the next run check
whether that process is alive - is unsafe on Windows. Python's ``os.kill(pid,
0)``, the usual liveness probe, does not send a signal on Windows: it calls
``TerminateProcess``. The "check" would kill whatever now owns that PID.

So the lock is an OS-level exclusive lock on an open file handle
(``msvcrt.locking`` on Windows, ``fcntl.flock`` elsewhere). This is stronger
than a PID file in the way that matters most: **the kernel releases it when the
process dies**, however it died. There is no stale-lock class of bug to recover
from, because a crashed run leaves a lock file that is not locked, and the next
run takes it immediately. The file's contents are diagnostics only - who held
it, since when - and are never used to decide whether the lock is free.
"""
from __future__ import annotations

import json
import logging
import os
import socket
from pathlib import Path
from types import TracebackType

from exceptions import RunLockUnavailable

logger = logging.getLogger("easytime.lock")

try:  # Windows
    import msvcrt

    _HAVE_MSVCRT = True
except ImportError:  # POSIX (CI, developer machines)
    msvcrt = None  # type: ignore[assignment]
    _HAVE_MSVCRT = False

try:
    import fcntl

    _HAVE_FCNTL = True
except ImportError:
    fcntl = None  # type: ignore[assignment]
    _HAVE_FCNTL = False

# Windows byte-range locks are MANDATORY, not advisory: a locked region cannot
# even be READ through another handle. Locking byte 0 would therefore make the
# diagnostics unreadable - including by the very run that wants to report who is
# holding the lock. So the lock is taken on a byte far past any content the file
# will ever have (Windows permits locking beyond EOF), leaving offset 0 onwards
# free for the JSON. POSIX flock is advisory and whole-file, and needs no such
# trick.
_LOCK_OFFSET = 1 << 30


class RunLock:
    """An exclusive, self-releasing lock on one file.

        with RunLock(path, run_id=run_id):
            ...

    Raises ``RunLockUnavailable`` if another run already holds it.
    """

    def __init__(self, path: Path, *, run_id: str = "", mode: str = "") -> None:
        self.path = Path(path)
        self.run_id = run_id
        self.mode = mode
        self._fd: int | None = None

    # -- context manager -----------------------------------------------------
    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()

    @property
    def held(self) -> bool:
        return self._fd is not None

    # -- acquire / release ---------------------------------------------------
    def acquire(self) -> None:
        """Take the lock, or raise ``RunLockUnavailable``.

        The file is opened (creating it if needed) and then locked. Opening
        never blocks and never truncates another holder's diagnostics: the
        contents are only rewritten once the lock is actually ours.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            _lock_exclusive_nonblocking(fd)
        except OSError as exc:
            os.close(fd)
            raise RunLockUnavailable(
                f"Another connector run holds {self.path}"
                f"{_describe_holder(self.path)}. This invocation is exiting without "
                "doing anything - the active run covers the same window."
            ) from exc

        self._fd = fd
        self._write_diagnostics()
        logger.info("lock acquired path=%s run_id=%s", self.path, self.run_id)

    def release(self) -> None:
        """Release and close. Idempotent, and never raises.

        The lock file itself is deliberately left behind. Deleting it would
        open a window in which two runs each create their own fresh file and
        both "succeed", which is the exact failure this class exists to
        prevent. An empty leftover file costs nothing.
        """
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            _unlock(fd)
        except OSError:  # pragma: no cover - the close below releases it anyway
            pass
        finally:
            os.close(fd)
        logger.info("lock released path=%s run_id=%s", self.path, self.run_id)

    def _write_diagnostics(self) -> None:
        """Record who holds the lock. Advisory information only.

        Never a secret, and never read back as a liveness signal - the OS lock
        is the only thing that decides whether the lock is free.
        """
        payload = json.dumps(
            {
                "pid": os.getpid(),
                "host": _hostname(),
                "run_id": self.run_id,
                "mode": self.mode,
                "acquired_at": _now_text(),
            }
        )
        assert self._fd is not None
        try:
            os.lseek(self._fd, 0, os.SEEK_SET)
            os.write(self._fd, payload.encode("utf-8"))
            os.ftruncate(self._fd, len(payload))
        except OSError:  # pragma: no cover - diagnostics must never fail a run
            logger.debug("could not write lock diagnostics to %s", self.path)


# -- platform primitives -----------------------------------------------------
def _lock_exclusive_nonblocking(fd: int) -> None:
    """Take an exclusive lock, or raise OSError immediately.

    Both implementations are released automatically when the handle closes -
    including when the process is killed, which is the property that removes
    the whole stale-lock problem.
    """
    if _HAVE_MSVCRT:
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    elif _HAVE_FCNTL:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:  # pragma: no cover - no supported platform lacks both
        raise OSError("No file-locking primitive is available on this platform.")


def _unlock(fd: int) -> None:
    if _HAVE_MSVCRT:
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    elif _HAVE_FCNTL:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _describe_holder(path: Path) -> str:
    """" (pid 1234 on HOST since ...)" if the file says so, else empty.

    Best-effort and untrusted: a truncated or hand-edited file must not turn a
    clean "another run is active" exit into a crash.
    """
    try:
        raw = path.read_text(encoding="utf-8").strip()
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            return ""
        pid = data.get("pid")
        host = data.get("host")
        since = data.get("acquired_at")
        if pid is None:
            return ""
        return f" (pid {pid} on {host or 'this PC'} since {since or 'an unknown time'})"
    except (OSError, ValueError):
        return ""


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:  # pragma: no cover
        return "unknown"


def _now_text() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
