"""Wait for STS2 game state to reflect completed actions (animations / deals)."""

from __future__ import annotations

import time
from typing import Any

from plugins.sts2.visibility import state_fingerprint


def action_needs_settle(action: str) -> bool:
    a = (action or "").strip().lower()
    if not a or a in ("__wait__", "__pause__", "status"):
        return False
    return True


def _still_settling(pre: dict, cur: dict, action: str) -> bool:
    """True while cur likely still shows pre-animation snapshot."""
    if state_fingerprint(pre) == state_fingerprint(cur):
        return True
    st = str(cur.get("state_type") or "")
    if st in ("monster", "elite", "boss"):
        from plugins.sts2.combat_brain import combat_should_wait

        if combat_should_wait(cur):
            return True
    return False


def wait_for_settled_state(
    pre_state: dict | None,
    action: str,
    *,
    max_wait_sec: float | None = None,
    poll_sec: float | None = None,
    min_wait_sec: float | None = None,
) -> tuple[dict | None, dict[str, Any]]:
    """
  Poll STS2MCP until state differs from pre-action (or timeout).

  Returns (latest_state, meta) with keys settled, polls, elapsed_ms, note.
    """
    from plugins.sts2 import client as sts2_client
    from plugins.sts2.config import load_sts2_config

    meta: dict[str, Any] = {
        "settled": True,
        "polls": 0,
        "elapsed_ms": 0,
        "action": action,
    }
    if not action_needs_settle(action) or not pre_state:
        try:
            status, cur = sts2_client.get_singleplayer_state(fmt="json")
            if status == 200 and isinstance(cur, dict):
                return cur, meta
        except Exception:
            pass
        return None, meta

    cfg = load_sts2_config()
    try:
        max_w = float(
            max_wait_sec
            if max_wait_sec is not None
            else cfg.get("state_settle_max_seconds", 2.8)
        )
    except (TypeError, ValueError):
        max_w = 2.8
    try:
        poll = float(
            poll_sec
            if poll_sec is not None
            else cfg.get("state_settle_poll_seconds", 0.12)
        )
    except (TypeError, ValueError):
        poll = 0.12
    try:
        min_w = float(
            min_wait_sec
            if min_wait_sec is not None
            else cfg.get("state_settle_min_seconds", 0.28)
        )
    except (TypeError, ValueError):
        min_w = 0.28

    poll = max(0.05, min(poll, 0.5))
    max_w = max(min_w, min(max_w, 8.0))
    min_w = max(0.0, min(min_w, max_w))

    t0 = time.monotonic()
    deadline = t0 + max_w
    latest: dict | None = None
    polls = 0

    time.sleep(min_w)

    while time.monotonic() < deadline:
        polls += 1
        try:
            status, cur = sts2_client.get_singleplayer_state(fmt="json")
        except Exception as exc:
            meta["settled"] = False
            meta["note"] = f"poll failed: {exc}"
            meta["polls"] = polls
            meta["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
            return latest, meta

        if status == 200 and isinstance(cur, dict):
            latest = cur
            if not _still_settling(pre_state, cur, action):
                meta["settled"] = True
                meta["polls"] = polls
                meta["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
                return latest, meta

        time.sleep(poll)

    meta["settled"] = False
    meta["polls"] = polls
    meta["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
    meta["note"] = (
        "状态在限时内未相对出牌前变化，可能仍在动画中或动作未生效；"
        "请谨慎再出牌或再 sts2_get_state。"
    )
    return latest, meta
