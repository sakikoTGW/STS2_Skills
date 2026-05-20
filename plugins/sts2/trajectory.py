"""Append-only JSONL trajectory logging."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from plugins.sts2.storage import new_trajectory_path

_lock = threading.Lock()
_current_path: Optional[Path] = None


def start_session() -> Path:
    global _current_path
    with _lock:
        _current_path = new_trajectory_path()
        return _current_path


def current_path() -> Optional[Path]:
    return _current_path


def log_event(
    event_type: str,
    payload: Dict[str, Any],
    *,
    path: Optional[Path] = None,
) -> None:
    target = path or _current_path
    if target is None:
        target = start_session()
    row = {"type": event_type, **payload}
    line = json.dumps(row, ensure_ascii=False)
    with _lock:
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
