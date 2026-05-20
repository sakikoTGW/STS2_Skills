"""Manual hand-play: legal action menu + faithful sts2_act (no silent rewrites)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

_COMBAT = frozenset({"monster", "elite", "boss", "hand_select"})


def target_only_correction(requested: dict, validated: dict) -> bool:
    """True when validate only filled combat target, not card_index/action."""
    if str(requested.get("action") or "") != "play_card":
        return False
    if str(validated.get("action") or "") != "play_card":
        return False
    req = {k: v for k, v in requested.items() if k != "target"}
    val = {k: v for k, v in validated.items() if k != "target"}
    return req == val and requested != validated


def _agent_or_manual_play() -> bool:
    try:
        from plugins.sts2.play_mode import agent_play_mode
        from plugins.sts2.manual_mode import manual_mode_enabled

        return manual_mode_enabled() or agent_play_mode()
    except Exception:
        return False


def build_legal_actions(state: dict) -> Optional[List[Dict[str, Any]]]:
    """Enumerated actions the model may copy into sts2_act (agent / manual play)."""
    if not _agent_or_manual_play():
        return None
    if not state:
        return None
    st = str(state.get("state_type") or "")
    if st not in _COMBAT:
        return None

    from plugins.sts2.combat_brain import combat_should_wait, _affordable, _cost
    from plugins.sts2.combat_survival_gate import must_survive_turn, play_card_would_lethal

    if combat_should_wait(state):
        return [{"action": "__wait__", "label": "敌方回合等待"}]

    try:
        from plugins.sts2.play_mode import agent_play_mode

        agent_only = agent_play_mode()
    except Exception:
        agent_only = False

    if not agent_only:
        try:
            from plugins.sts2.combat_survival_gate import potion_required_before_play

            pot_first = potion_required_before_play(state)
            if pot_first:
                return [
                    {
                        **pot_first,
                        "label": "use_potion (必死线·须先用药) "
                        + json.dumps(pot_first, ensure_ascii=False),
                        "allowed": True,
                    },
                    {"action": "end_turn", "label": "end_turn ⛔勿先结束", "allowed": False},
                ]
        except Exception:
            pass

    player = state.get("player") or {}
    hand = player.get("hand") or []
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0

    actions: List[Dict[str, Any]] = []
    must_survive = must_survive_turn(state)
    for card in hand:
        if not card.get("can_play", True):
            continue
        try:
            if _cost(card) > energy:
                continue
        except Exception:
            pass
        idx = card.get("index")
        name = card.get("name") or card.get("id") or "?"
        body: Dict[str, Any] = {"action": "play_card", "card_index": idx}
        lethal = play_card_would_lethal(state, body)
        label = f"play_card index={idx} {name}"
        from plugins.sts2.combat_brain import _card_is_block

        if lethal:
            if agent_only:
                label += " ⚠送死风险(你判断)"
                actions.append(
                    {**body, "label": label, "allowed": True, "warning": "lethal"}
                )
            else:
                label += " ⛔必死线禁止"
                actions.append(
                    {
                        **body,
                        "label": label,
                        "allowed": False,
                        "reason": "净入伤≥有效HP，须叠防/用药",
                    }
                )
            continue
        if must_survive and not _card_is_block(card):
            if agent_only:
                label += " ⚠须先防?(你判断)"
                actions.append(
                    {**body, "label": label, "allowed": True, "warning": "survive"}
                )
            else:
                label += " ⛔须先防"
                actions.append(
                    {
                        **body,
                        "label": label,
                        "allowed": False,
                        "reason": "必死线须先打出格挡",
                    }
                )
            continue
        actions.append({**body, "label": label, "allowed": True})

    playable_count = sum(1 for a in actions if a.get("allowed"))
    if playable_count == 0 and must_survive:
        try:
            from plugins.sts2.combat_survival_gate import pick_survival_card

            hint = pick_survival_card(state)
            if hint:
                actions.append(
                    {
                        **hint,
                        "label": "建议(须你确认后 sts2_act): " + json.dumps(hint, ensure_ascii=False),
                        "allowed": True,
                        "hint_only": True,
                    }
                )
        except Exception:
            pass

    actions.append({"action": "end_turn", "label": "end_turn", "allowed": True})
    return actions


def attach_manual_act_fields(payload: dict) -> dict:
    """Top-level legal_actions + short manual contract on get_state."""
    if not _agent_or_manual_play() or not isinstance(payload, dict):
        return payload
    legal = build_legal_actions(payload)
    if legal is None:
        return payload
    out = dict(payload)
    out["legal_actions"] = legal
    allowed = [a for a in legal if a.get("allowed") and not a.get("hint_only")]
    try:
        from plugins.sts2.play_mode import agent_play_mode

        mode = "Agent带脑" if agent_play_mode() else "手操"
    except Exception:
        mode = "手操"
    out["manual_contract"] = (
        f"{mode}：sts2_act 必须逐字使用 legal_actions 里 allowed=true 的一条；"
        "校验层不会替你改 card_index（仅可补 target）。"
        f" 当前可执行 {len(allowed)} 个出牌 + end_turn。"
    )
    return out
