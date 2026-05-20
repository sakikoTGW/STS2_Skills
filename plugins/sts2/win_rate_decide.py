"""通关模式决策：评分战斗 + 规则运营，LLM 失败也不停工。"""

from __future__ import annotations

from typing import Optional

_COMBAT = frozenset({"monster", "elite", "boss"})


def decide_win_rate(
    state: dict,
    *,
    user_hint: str = "",
    memory: str = "",
) -> tuple[str, dict]:
    """Single entry for autopilot — optimize FULL_RUN_CLEARED, not commentary."""
    from plugins.sts2.decision import (
        _coerce_action,
        _pick_map_node,
        _plan_commentary,
        _rule_action,
    )
    from plugins.sts2.visibility import describe_action, describe_situation

    st = str(state.get("state_type") or "")
    prefix = (memory + "\n").strip() if memory else ""
    tag = "【通关模式】"

    if st in _COMBAT:
        from plugins.sts2.action_validate import validate_action
        from plugins.sts2.combat_scorer import decide_combat_scored

        body = validate_action(state, decide_combat_scored(state))
        line = f"{tag} 评分战斗\n▶ {describe_action(state, body)}"
        return (prefix + line + "\n" + describe_situation(state)).strip(), body

    if st == "hand_select":
        from plugins.sts2.hand_select_brain import decide_hand_select

        body = decide_hand_select(state)
        return (prefix + tag + " 选牌\n▶ " + describe_action(state, body)).strip(), body

    if st == "bundle_select":
        from plugins.sts2.bundle_select_brain import decide_bundle_select

        body = decide_bundle_select(state)
        return (prefix + tag + " 卷轴\n▶ " + describe_action(state, body)).strip(), body

    if st == "rewards":
        from plugins.sts2.rewards_screen import decide_rewards_screen

        body = decide_rewards_screen(state)
        return (prefix + tag + " 领奖\n▶ " + describe_action(state, body)).strip(), body

    if st in ("treasure", "fake_merchant"):
        from plugins.sts2.treasure_rewards import decide_treasure_action

        body = decide_treasure_action(state)
        return (prefix + tag + " 宝箱\n▶ " + describe_action(state, body)).strip(), body

    if st == "card_reward":
        from plugins.sts2.card_pick_brain import rule_card_reward_fallback

        comm, body = rule_card_reward_fallback(state)
        return (prefix + tag + " " + comm).strip(), body

    if st == "card_select":
        from plugins.sts2.decision import _pick_best_card
        from plugins.sts2.reward_cards import offer_reward_cards

        cards = offer_reward_cards(state)
        if cards:
            ix = _pick_best_card(cards)
            body = {"action": "select_card", "index": ix if ix is not None else 0}
        else:
            body = {"action": "confirm_selection"}
        return (prefix + tag + "\n▶ " + describe_action(state, body)).strip(), body

    if st == "map":
        opts = (state.get("map") or {}).get("next_options") or state.get("next_options") or []
        if opts:
            body = _pick_map_node(opts, state)
            from plugins.sts2.act1_clear import hp_ratio, run_floor
            from plugins.sts2.run_victory import run_act

            act = run_act(state)
            floor = run_floor(state)
            hr = hp_ratio(state)
            comm = (
                f"{tag} Act{act} F{floor} HP{hr:.0%} → "
                f"选路 #{body.get('index')}（精英门禁/营火优先）"
            )
            return (prefix + comm).strip(), body

    ruled = _rule_action(state)
    if ruled:
        return (prefix + tag + "\n" + _plan_commentary(state, ruled)).strip(), ruled

    if st == "event":
        ev = state.get("event") or {}
        if ev.get("in_dialogue"):
            body = {"action": "advance_dialogue"}
        else:
            opts = [o for o in (ev.get("options") or []) if isinstance(o, dict) and not o.get("is_locked")]
            if opts:
                body = {"action": "choose_event_option", "index": opts[0].get("index", 0)}
            else:
                body = {"action": "proceed"}
        return (prefix + tag + "\n▶ " + describe_action(state, body)).strip(), body

    body = _coerce_action(state, {"action": "proceed"})
    return (prefix + tag + " proceed").strip(), body
