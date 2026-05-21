"""Force card reward / card select / rewards — bypass broken LLM on pick screens."""

from __future__ import annotations

from typing import Any

_CARD_STATES = frozenset({"card_reward", "card_select", "rewards"})


def is_card_flow_state(state: dict) -> bool:
    return str(state.get("state_type") or "") in _CARD_STATES


def decide_card_flow(state: dict) -> tuple[str, dict[str, Any]]:
    """Always return a legal pick/claim action for reward screens."""
    from plugins.sts2.action_validate import validate_action  # noqa: WPS433

    st = str(state.get("state_type") or "")

    if st == "rewards":
        from plugins.sts2.rewards_screen import decide_rewards_screen  # noqa: WPS433

        body = decide_rewards_screen(state)
        return "【强制·战后奖励】先领完再离开", validate_action(state, body)

    if st == "card_reward":
        from plugins.sts2.card_pick_brain import rule_card_reward_fallback  # noqa: WPS433

        comm, body = rule_card_reward_fallback(state)
        body = validate_action(state, body)
        if body.get("action") == "proceed":
            body = {"action": "select_card_reward", "card_index": 0}
        return f"【强制·选卡奖励】{comm}", body

    if st == "card_select":
        from plugins.sts2.card_pick_brain import rule_card_select_fallback  # noqa: WPS433

        comm, body = rule_card_select_fallback(state)
        return f"【强制·选牌】{comm}", validate_action(state, body)

    return "", {"action": "__wait__"}


async def run_card_flow_until_clear(
    plugin_cfg: dict,
    *,
    max_steps: int = 6,
) -> dict[str, Any] | None:
    """Execute card/reward actions until we leave pick screens."""
    from .sts2_skills_bridge import ensure_skills

    ensure_skills(plugin_cfg, base_url=plugin_cfg.get("base_url"))
    import asyncio

    from plugins.sts2 import client as sts2_client  # noqa: WPS433

    last: dict[str, Any] = {}
    for _ in range(max_steps):
        status, state = await asyncio.to_thread(
            sts2_client.get_singleplayer_state, fmt="json"
        )
        if status != 200 or not isinstance(state, dict):
            return last or {"success": False, "error": f"HTTP {status}"}
        if not is_card_flow_state(state):
            return last or None

        comm, body = decide_card_flow(state)
        if body.get("action") in ("__wait__", "__pause__", ""):
            break

        act_status, act_payload = await asyncio.to_thread(
            sts2_client.post_singleplayer_action, body
        )
        ok = act_status == 200
        if isinstance(act_payload, dict) and act_payload.get("status") == "error":
            ok = False
        last = {
            "success": ok,
            "commentary": comm,
            "action": body,
            "state_type": state.get("state_type"),
            "http_status": act_status,
            "body": act_payload,
            "forced_card_flow": True,
        }
        if not ok:
            break
        await asyncio.sleep(0.35)
    return last if last else None


def run_card_flow_until_clear_sync(
    plugin_cfg: dict,
    *,
    max_steps: int = 6,
) -> dict[str, Any] | None:
    """Sync variant for AutoplayController._single_step hook."""
    import time

    from .sts2_skills_bridge import ensure_skills

    ensure_skills(plugin_cfg, base_url=plugin_cfg.get("base_url"))
    from plugins.sts2 import client as sts2_client  # noqa: WPS433

    last: dict[str, Any] = {}
    for _ in range(max_steps):
        status, state = sts2_client.get_singleplayer_state(fmt="json")
        if status != 200 or not isinstance(state, dict):
            return last or {"success": False, "error": f"HTTP {status}"}
        if not is_card_flow_state(state):
            return last or None

        comm, body = decide_card_flow(state)
        if body.get("action") in ("__wait__", "__pause__", ""):
            break

        act_status, act_payload = sts2_client.post_singleplayer_action(body)
        ok = act_status == 200
        if isinstance(act_payload, dict) and act_payload.get("status") == "error":
            ok = False
        last = {
            "success": ok,
            "commentary": comm,
            "action": body,
            "state_type": state.get("state_type"),
            "http_status": act_status,
            "body": act_payload,
            "forced_card_flow": True,
        }
        if not ok:
            break
        time.sleep(0.35)
    return last if last else None
