"""Act1 guaranteed-clear policy — objective mistakes + rule combat (agent-play)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from plugins.sts2.act1_clear import hp_ratio, pick_map_node, run_floor, _option_label


def act1_guarantee_enabled() -> bool:
    if os.environ.get("HERMES_STS2_ACT1_GUARANTEE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    try:
        from plugins.sts2.play_mode import agent_play_mode, autopilot_active

        if agent_play_mode() or autopilot_active():
            return True
    except Exception:
        pass
    try:
        from plugins.sts2.study_mode import is_study_mode

        return is_study_mode()
    except Exception:
        return False


def act1_guard_mode() -> str:
    """objective = map/rewards/rest only; full = include rule combat override; off = none."""
    raw = os.environ.get("HERMES_STS2_ACT1_GUARD", "").strip().lower()
    if raw in ("objective", "map", "full", "off", "combat"):
        return "map" if raw == "map" else raw
    try:
        from plugins.sts2.config import load_sts2_config
        from plugins.sts2.study_mode import is_study_mode

        cfg = load_sts2_config()
        mode = str(cfg.get("act1_guard", "objective")).strip().lower()
        if is_study_mode() and cfg.get("act1_guard_autopilot") is not None:
            mode = str(cfg.get("act1_guard_autopilot", mode)).strip().lower()
        return mode if mode in ("objective", "map", "full", "off", "combat") else "objective"
    except Exception:
        return "objective"


def _run_act(state: dict) -> int:
    try:
        from plugins.sts2.run_victory import run_act

        return int(run_act(state))
    except (TypeError, ValueError):
        return 1


def _is_elite_option(option: dict) -> bool:
    return "elite" in _option_label(option)


def veto_objective_mistake(state: dict, body: dict) -> Optional[str]:
    """Human-readable reason if this action is objectively losing for Act1."""
    if not act1_guarantee_enabled() or _run_act(state) != 1:
        return None
    st = str(state.get("state_type") or "")
    action = str(body.get("action") or "")
    ratio = hp_ratio(state)
    floor = run_floor(state)

    if st == "map" and action == "choose_map_node":
        opts = (state.get("map") or {}).get("next_options") or state.get("next_options") or []
        try:
            ix = int(body.get("index", -1))
        except (TypeError, ValueError):
            return "地图 index 无效"
        chosen = next((o for o in opts if isinstance(o, dict) and o.get("index") == ix), None)
        if chosen and _is_elite_option(chosen):
            if ratio < 0.5:
                return f"Act1 HP{int(100*ratio)}%<50% 禁止精英"
            if floor < 12 and ratio < 0.72:
                return f"Act1 第{floor}层 HP{int(100*ratio)}%<72% 禁止精英"
        return None

    if st == "rewards" and action == "proceed":
        from plugins.sts2.rewards_screen import rewards_unclaimed

        if rewards_unclaimed(state):
            return "战后奖励未领完禁止 proceed"
        return None

    if st == "event" and action == "menu_select":
        return "事件屏禁止 menu_select"

    return None


def coerce_act1_action(state: dict, body: dict) -> tuple[dict, bool, str]:
    """Return (body, was_coerced, note). Act1 only."""
    if not act1_guarantee_enabled() or _run_act(state) != 1:
        return body, False, ""
    mode = act1_guard_mode()
    if mode == "off":
        return body, False, ""
    st = str(state.get("state_type") or "")
    action = str(body.get("action") or "")

    if st == "map":
        opts = (state.get("map") or {}).get("next_options") or state.get("next_options") or []
        best = pick_map_node(opts, state)
        if action != best.get("action") or body.get("index") != best.get("index"):
            return best, True, "Act1 选路保底：已改为最优节点"
        return body, False, ""

    if st == "rewards":
        from plugins.sts2.rewards_screen import decide_rewards_screen

        best = decide_rewards_screen(state)
        if action != best.get("action") or body.get("index") != best.get("index"):
            return best, True, "Act1 奖励屏：须领完再离开"
        return body, False, ""

    if st == "rest_site":
        from plugins.sts2.action_validate import _fix_rest_site

        best = _fix_rest_site(state, body)
        if best != body:
            return best, True, "Act1 营火：低血优先回血"
        return body, False, ""

    if st in ("monster", "elite", "boss", "hand_select"):
        if mode in ("objective", "map"):
            from plugins.sts2.combat_brain import combat_should_wait

            if combat_should_wait(state) and action != "__wait__":
                return {"action": "__wait__"}, True, "敌方回合须等待"
            return body, False, ""
        from plugins.sts2.combat_brain import combat_should_wait, decide_combat

        if combat_should_wait(state):
            if action != "__wait__":
                return {"action": "__wait__"}, True, "敌方回合须等待"
            return body, False, ""
        best = decide_combat(state, apply_lessons=True)
        if action == "end_turn":
            from plugins.sts2.combat_brain import combat_should_end_turn

            if not combat_should_end_turn(state):
                return best, True, "还有能量/可出牌，不可 end_turn"
        if action == "play_card" and best.get("action") == "play_card":
            try:
                if int(body.get("card_index", -999)) != int(best.get("card_index", -998)):
                    return best, True, "Act1 战斗保底：已改为规则最优出牌"
            except (TypeError, ValueError):
                return best, True, "Act1 战斗保底"
        if best.get("action") != action:
            return best, True, "Act1 战斗保底"
        return body, False, ""

    if st == "card_reward" and mode == "full":
        from plugins.sts2.card_pick_brain import rule_card_reward_fallback

        _comm, best = rule_card_reward_fallback(state)
        if best and best != body:
            return best, True, "Act1 选牌保底"
        return body, False, ""

    if st == "game_over" or st == "menu":
        from plugins.sts2.run_flow import next_menu_action

        nxt = next_menu_action(state)
        if nxt and nxt != body:
            return nxt, True, "Act1 菜单：开新铁甲局"
        return body, False, ""

    return body, False, ""
