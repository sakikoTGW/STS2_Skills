"""Single-driver guard: autoplay thread vs manual sts2_act."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_mode: str | None = None
_tls = threading.local()


def active_mode() -> str | None:
    global _mode
    with _lock:
        return _mode


def acquire(mode: str) -> bool:
    global _mode
    if mode == "autoplay":
        try:
            from plugins.sts2.process_lock import try_acquire
            from plugins.sts2.storage import sts2_home

            if not try_acquire(sts2_home() / ".autoplay.lock", label="autoplay"):
                return False
        except OSError:
            return False
    with _lock:
        if _mode is not None and _mode != mode:
            if mode == "autoplay":
                from plugins.sts2.process_lock import release as release_pl

                release_pl()
            return False
        _mode = mode
        return True


def release(mode: str) -> None:
    global _mode
    with _lock:
        if _mode == mode:
            _mode = None
    if mode == "autoplay":
        try:
            from plugins.sts2.process_lock import release as release_pl

            release_pl()
        except OSError:
            pass


def set_internal_act(active: bool) -> None:
    _tls.internal_act = active


def is_internal_act() -> bool:
    return bool(getattr(_tls, "internal_act", False))


def manual_act_blocked() -> str | None:
    # File-based kill switch: create ~/.hermes/sts2/.unlock to bypass
    try:
        from plugins.sts2.storage import sts2_home
        if (sts2_home() / ".unlock").is_file():
            return None
    except Exception:
        pass
    if is_internal_act():
        return None
    try:
        from plugins.sts2.process_lock import foreign_lock_held
        from plugins.sts2.storage import sts2_home

        lock = sts2_home() / ".autoplay.lock"
        if foreign_lock_held(lock):
            return (
                "sts2_act blocked: autoplay lock held by another process "
                "(stop the other Hermes/autoplay first)."
            )
    except Exception:
        pass
    with _lock:
        if _mode:
            return (
                f"sts2_act blocked while sts2 {_mode} is active (single-driver). "
                "Use sts2_autoplay action=stop first — do not alternate sts2_act with autoplay."
            )
    return None
