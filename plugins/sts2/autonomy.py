"""Until FULL_RUN_CLEARED: no pauses, no user questions."""

from __future__ import annotations

from typing import Any

from plugins.sts2.config import load_sts2_config


def full_run_cleared() -> bool:
    """Check victory marker without calling load_sts2_config (avoids import cycle)."""
    from hermes_constants import get_hermes_home

    from plugins.sts2.run_victory import victory_file_name

    return (get_hermes_home() / "sts2" / victory_file_name()).is_file()


def autopilot_until_victory(cfg: dict[str, Any] | None = None) -> bool:
    """True while we must run without asking the human."""
    if full_run_cleared():
        return False
    merged = cfg if cfg is not None else load_sts2_config()
    if merged.get("autopilot_until_victory") is False:
        return False
    return bool(merged.get("autopilot_until_victory", True))


def resolve_without_user(state: dict) -> tuple[str, dict]:
    """Pick a legal action when we must not pause for the human."""
    from plugins.sts2.action_validate import validate_action
    from plugins.sts2.decision import _coerce_action, _rule_action, _safe_fallback

    commentary, body = _safe_fallback(state)
    body = validate_action(state, body)
    body = _coerce_action(state, body)
    if body.get("action") not in ("__pause__", ""):
        return commentary, body

    ruled = _rule_action(state)
    if ruled:
        ruled = validate_action(state, _coerce_action(state, ruled))
        return commentary or "规则自动推进。", ruled

    st = str(state.get("state_type") or "")
    return f"全自动推进 ({st})", {"action": "proceed"}


def clear_user_wait_state() -> None:
    """Drop pending questions and pause flags (marathon / supervisor)."""
    from plugins.sts2.storage import pending_question_path

    pending_question_path().unlink(missing_ok=True)
