"""Learning during LLM autopilot / agent-play (not only manual_mode)."""

from __future__ import annotations

from typing import Any


def agent_learn_enabled() -> bool:
    from plugins.sts2.config import load_sts2_config

    cfg = load_sts2_config()
    if not cfg.get("agent_auto_learn", True):
        return False
    try:
        from plugins.sts2.autoplay import get_controller

        st = get_controller().status()
        if st.get("studying") or st.get("running"):
            return True
    except Exception:
        pass
    try:
        from plugins.sts2.play_mode import agent_play_mode

        return agent_play_mode()
    except Exception:
        return False


def tick_after_step(
    state: dict,
    *,
    action: dict | None = None,
) -> dict[str, Any]:
    """Reflect on state transitions during autopilot (death / act clear)."""
    if not agent_learn_enabled() or not isinstance(state, dict):
        return {}
    try:
        from plugins.sts2.manual_learn import tick

        return tick(state, action=action)
    except Exception:
        return {}
