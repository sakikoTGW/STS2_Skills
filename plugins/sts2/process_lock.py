"""Cross-process exclusive lock (supervisor singleton, shared autoplay driver)."""

from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path

_lock_path: Path | None = None
_lock_fh = None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _try_lock_fd(fd: int) -> bool:
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock_fd(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def holder_pid(path: Path) -> int | None:
    try:
        text = Path(path).read_text(encoding="utf-8").strip().splitlines()
        if text:
            return int(text[0])
    except (OSError, ValueError):
        pass
    return None


def try_acquire(path: Path, *, label: str = "") -> bool:
    """Acquire lock file; return False if another live process holds it."""
    global _lock_path, _lock_fh
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        other = holder_pid(path)
        if other is not None and _pid_alive(other):
            return False
        try:
            path.unlink()
        except OSError:
            # Stale or corrupt lock (pid missing / holder exited without release)
            if other is None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    return False
            else:
                return False

    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileExistsError:
        other = holder_pid(path)
        if other is not None and not _pid_alive(other):
            try:
                path.unlink()
            except OSError:
                return False
            return try_acquire(path, label=label)
        return False

    fh = os.fdopen(fd, "a+", encoding="utf-8")
    if not _try_lock_fd(fh.fileno()):
        fh.close()
        try:
            path.unlink()
        except OSError:
            pass
        return False

    fh.write(f"{os.getpid()}\n{label}\n")
    fh.flush()
    _lock_path = path
    _lock_fh = fh
    return True


def release() -> None:
    global _lock_path, _lock_fh
    if _lock_fh is None:
        return
    path = _lock_path
    try:
        _unlock_fd(_lock_fh.fileno())
    finally:
        try:
            _lock_fh.close()
        except OSError:
            pass
        _lock_path = None
        _lock_fh = None
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


atexit.register(release)
