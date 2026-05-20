"""Study autoplay: LLM decisions each step + cross-run lessons."""

from __future__ import annotations

import threading

_active = threading.local()
_global_study = False


def set_study_mode(on: bool) -> None:
    global _global_study
    _global_study = bool(on)
    _active.enabled = bool(on)


def is_study_mode() -> bool:
    if _global_study:
        return True
    return bool(getattr(_active, "enabled", False))
