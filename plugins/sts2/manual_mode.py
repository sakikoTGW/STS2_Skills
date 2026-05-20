"""Manual play vs background autoplay — user hand-controls unless they ask for auto."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from plugins.sts2.storage import sts2_home

_FLAG = ".manual_play"


def manual_mode_enabled() -> bool:
    """True = do not auto-start or resume background autopilot; sts2_act is allowed."""
    if os.environ.get("HERMES_STS2_MANUAL", "").strip() in ("1", "true", "yes"):
        return True
    return (sts2_home() / _FLAG).is_file()


def set_manual_mode(enabled: bool) -> None:
    path = sts2_home() / _FLAG
    path.parent.mkdir(parents=True, exist_ok=True)
    if enabled:
        path.write_text(
            f"enabled_at={datetime.now(timezone.utc).isoformat()}\n"
            "Hermes STS2: hand play via sts2_get_state + sts2_act. "
            "Rule autopilot is permanently disabled; use sts2_get_state + sts2_act.\n",
            encoding="utf-8",
        )
    else:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def release_all_driver_locks() -> None:
    from plugins.sts2 import driver_lock

    driver_lock.release("autoplay")
    try:
        from plugins.sts2.process_lock import release as release_pl

        release_pl()
        (sts2_home() / ".autoplay.lock").unlink(missing_ok=True)
        (sts2_home() / ".supervisor.lock").unlink(missing_ok=True)
    except OSError:
        pass
