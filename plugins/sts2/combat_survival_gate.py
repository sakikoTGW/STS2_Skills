"""Survival-first combat gate — net damage vs HP, block/potion before attacks."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from plugins.sts2.combat_brain import (
    _affordable,
    _card_is_attack,
    _card_is_block,
    _cost,
    _play_card,
    _target_entity_id,
    combat_should_wait,
    estimate_block_gain,
    estimate_card_damage,
    incoming_attack_damage,
    incoming_attack_damage_excluding,
    net_incoming_damage,
)


def relic_turn_hp_loss(state: dict) -> int:
    """Start-of-turn HP loss from relics/powers (e.g. Crimson Mantle)."""
    total = 0
    player = state.get("player") or {}
    blob_parts: List[str] = []
    for key in ("powers", "relics", "buffs"):
        for p in player.get(key) or []:
            if isinstance(p, dict):
                blob_parts.append(
                    str(p.get("name") or "")
                    + str(p.get("description") or "")
                    + str(p.get("id") or "")
                )
    blob = " ".join(blob_parts).lower()
    for pat in (
        r"每回合.*失去\s*(\d+)\s*点?生命",
        r"lose\s+(\d+)\s+hp.*turn",
        r"at the start of your turn.*(\d+).*hp",
        r"绯红.*(\d+)",
    ):
        m = re.search(pat, blob, re.I)
        if m:
            total += int(m.group(1))
    if "绯红披风" in blob or "crimson mantle" in blob:
        total = max(total, 1)
    return total


def survival_snapshot(state: dict) -> Dict[str, Any]:
    """Numbers the agent must read before any play_card."""
    if combat_should_wait(state):
        return {"active": False, "reason": "enemy_turn"}

    player = state.get("player") or {}
    try:
        hp = int(player.get("hp", player.get("current_hp", 0)))
        max_hp = int(player.get("max_hp", hp) or hp or 1)
        block = int(player.get("block", 0))
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        hp, max_hp, block, energy = 0, 1, 0, 0

    enemies = (state.get("battle") or {}).get("enemies") or []
    incoming = incoming_attack_damage(enemies)
    net = net_incoming_damage(incoming, block)
    dot = relic_turn_hp_loss(state)
    hp_after_dot = max(0, hp - dot)

    hand = player.get("hand") or []
    playable = _affordable(hand, energy)
    blocks = [c for c in playable if _card_is_block(c)]
    attacks = [c for c in playable if _card_is_attack(c)]

    block_gain_avail = sum(estimate_block_gain(c) for c in blocks[: max(1, energy)])
    projected_block = block + block_gain_avail
    projected_net = net_incoming_damage(incoming, projected_block)

    must_survive = incoming > 0 and net >= hp_after_dot and hp_after_dot > 0
    must_block_first = must_survive and bool(blocks)
    lethal_this_turn = net >= hp_after_dot

    return {
        "active": True,
        "hp": hp,
        "max_hp": max_hp,
        "block": block,
        "energy": energy,
        "incoming": incoming,
        "net": net,
        "relic_dot": dot,
        "hp_effective": hp_after_dot,
        "must_survive": must_survive,
        "must_block_first": must_block_first,
        "lethal_this_turn": lethal_this_turn,
        "block_gain_if_all_blocks": block_gain_avail,
        "projected_net_after_blocks": projected_net,
        "playable_blocks": len(blocks),
        "playable_attacks": len(attacks),
    }


def must_block_first(state: dict) -> bool:
    return bool(survival_snapshot(state).get("must_block_first"))


def must_survive_turn(state: dict) -> bool:
    return bool(survival_snapshot(state).get("must_survive"))


def _damage_to_enemy(card: dict, player: dict, enemy: dict) -> int:
    """Use visible block only — Skittish etc. come from wiki + powers, not guesses."""
    dmg = estimate_card_damage(card, player)
    try:
        e_blk = int(enemy.get("block", 0) or 0)
    except (TypeError, ValueError):
        e_blk = 0
    return max(0, dmg - e_blk)


def _attack_kill_reduces_lethal(state: dict, body: dict, card: dict) -> bool:
    """Killing targeted enemy drops incoming below effective HP."""
    if not _card_is_attack(card):
        return False
    target = body.get("target")
    enemies = (state.get("battle") or {}).get("enemies") or []
    living = [e for e in enemies if int(e.get("hp", 0) or 0) > 0]
    if not living:
        return False
    focus = None
    if target:
        focus = next(
            (e for e in living if str(e.get("entity_id") or e.get("id") or "") == str(target)),
            None,
        )
    if focus is None:
        focus = min(living, key=lambda e: int(e.get("hp", 9999)))
    try:
        need = int(focus.get("hp", 0) or 0)
    except (TypeError, ValueError):
        return False
    if _damage_to_enemy(card, state.get("player") or {}, focus) < need:
        return False
    eid = str(focus.get("entity_id") or focus.get("id") or "")
    player = state.get("player") or {}
    try:
        block = int(player.get("block", 0))
    except (TypeError, ValueError):
        block = 0
    after_in = incoming_attack_damage_excluding(enemies, eid)
    snap = survival_snapshot(state)
    hp_eff = int(snap.get("hp_effective", snap.get("hp", 0)))
    net_after = net_incoming_damage(after_in, block)
    return net_after < max(1, hp_eff)


def potion_required_before_play(state: dict) -> Optional[dict]:
    """Lethal turn: use energy/draw/heal potion before wasting blocks."""
    snap = survival_snapshot(state)
    if not snap.get("active") or not snap.get("lethal_this_turn"):
        return None
    if snap.get("projected_net_after_blocks", 999) < snap.get("hp_effective", 1):
        return None
    try:
        from plugins.sts2.combat_resources import prefer_potion_play

        pot = prefer_potion_play(state)
        if pot and str(pot.get("action")) == "use_potion":
            return pot
    except Exception:
        pass
    return None


def pick_survival_card(
    state: dict,
    *,
    preferred_index: Optional[int] = None,
) -> Optional[dict]:
    snap = survival_snapshot(state)
    if not snap.get("active"):
        return None

    player = state.get("player") or {}
    hand = player.get("hand") or []
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    playable = _affordable(hand, energy)
    blocks = sorted(
        [c for c in playable if _card_is_block(c)],
        key=lambda c: (-estimate_block_gain(c), _cost(c)),
    )

    if preferred_index is not None:
        pref = next((c for c in blocks if c.get("index") == preferred_index), None)
        if pref:
            return _play_card(pref, _target_entity_id((state.get("battle") or {}).get("enemies") or []))

    if blocks:
        return _play_card(blocks[0], _target_entity_id((state.get("battle") or {}).get("enemies") or []))

    if snap.get("lethal_this_turn"):
        try:
            from plugins.sts2.combat_resources import prefer_potion_play

            pot = prefer_potion_play(state)
            if pot:
                return pot
        except Exception:
            pass
    return None


def play_card_would_lethal(state: dict, body: dict) -> bool:
    """True if this play_card would send an attack on a must-survive turn."""
    if str(body.get("action") or "") != "play_card":
        return False
    if not must_survive_turn(state):
        return False
    hand = (state.get("player") or {}).get("hand") or []
    try:
        idx = int(body.get("card_index", -1))
    except (TypeError, ValueError):
        return True
    card = next((c for c in hand if c.get("index") == idx), None)
    if not card:
        return True
    if _card_is_block(card) and card.get("can_play", True):
        return False
    if _card_is_attack(card):
        if _attack_kill_reduces_lethal(state, body, card):
            return False
        return True
    return False


def forbid_non_survival_play(state: dict, body: dict) -> Optional[dict]:
    if str(body.get("action") or "") != "play_card":
        return None
    if not must_survive_turn(state):
        return None

    hand = (state.get("player") or {}).get("hand") or []
    try:
        idx = int(body.get("card_index", -1))
    except (TypeError, ValueError):
        idx = -1
    card = next((c for c in hand if c.get("index") == idx), None)
    if card and _card_is_block(card) and card.get("can_play", True):
        return None

    forced = pick_survival_card(state, preferred_index=idx if card and _card_is_block(card) else None)
    if forced:
        return forced
    return {"action": "__pause__"}


def resolve_play_card_correction(
    state: dict,
    requested: dict,
    validated: dict,
) -> Tuple[str, Optional[dict]]:
    """Decide whether to execute validated play_card after index change.

    Returns (policy, body):
      ok — execute validated unchanged
      survival_override — execute validated (saved lethal mistake)
      block_post — do NOT post; return error to caller
      index_drift — do NOT post; force get_state
    """
    if str(requested.get("action") or "") != "play_card":
        return "ok", validated
    if str(validated.get("action") or "") != "play_card":
        return "ok", validated

    try:
        req_idx = int(requested.get("card_index", -999))
        exec_idx = int(validated.get("card_index", -999))
    except (TypeError, ValueError):
        return "ok", validated
    if req_idx == exec_idx:
        return "ok", validated

    hand = (state.get("player") or {}).get("hand") or []
    req_card = next((c for c in hand if c.get("index") == req_idx), None)
    exec_card = next((c for c in hand if c.get("index") == exec_idx), None)

    if must_survive_turn(state):
        if exec_card and _card_is_block(exec_card):
            return "survival_override", validated
        if (req_card and _card_is_block(req_card)) or (exec_card and _card_is_attack(exec_card)):
            return "block_post", None

    return "index_drift", None


def survival_alert_line(state: dict) -> str:
    """One line for situation / tool summary — model often skips long play_brief."""
    snap = survival_snapshot(state)
    if not snap.get("active"):
        if snap.get("reason") == "enemy_turn":
            return "⏸ 敌方回合：仅 __wait__"
        return ""
    if snap.get("lethal_this_turn"):
        pot_first = potion_required_before_play(state)
        nxt = pot_first or pick_survival_card(state)
        act = json.dumps(nxt, ensure_ascii=False) if nxt else "use_potion 或 end_turn"
        tag = "先用药" if pot_first else "先防/药"
        return (
            f"⛔必死线({tag}) 净入伤{snap['net']}≥HP{snap['hp_effective']} "
            f"(意图{snap['incoming']} 格挡{snap['block']}) → {act}"
        )
    if snap.get("incoming") == 0:
        return "✓ 本回合无攻击意图，可输出"
    return f"净入伤{snap['net']}<HP{snap['hp_effective']}，仍须用尽能量"


def format_survival_gate_block(state: dict) -> str:
    snap = survival_snapshot(state)
    if not snap.get("active"):
        if snap.get("reason") == "enemy_turn":
            return "【生存闸门】敌方回合 — 仅 __wait__，禁止 play_card/end_turn。"
        return ""

    lines = [
        "【生存闸门·出牌前必读】",
        f"  意图伤害合计≈{snap['incoming']} | 格挡{snap['block']} | "
        f"净入伤{snap['net']} | HP{snap['hp']}/{snap['max_hp']}",
    ]
    if snap.get("relic_dot"):
        lines.append(
            f"  回合开始自损≈{snap['relic_dot']} → 有效HP≈{snap['hp_effective']}"
        )
    if snap.get("lethal_this_turn"):
        pot_first = potion_required_before_play(state)
        nxt = pot_first or pick_survival_card(state)
        if pot_first:
            lines.append(
                "  ⛔ 叠防仍不够：必须先 use_potion（能量/抽牌/治疗类）。"
                f"  建议: {json.dumps(pot_first, ensure_ascii=False)}"
            )
        else:
            lines.append(
                "  ⛔ 净入伤≥有效HP：禁止送死攻击；先防/药。"
                f"  建议下一动: {json.dumps(nxt, ensure_ascii=False) if nxt else 'use_potion'}"
            )
        lines.append(
            "  例外：若斩杀可使下回合总意图伤害<HP，可打该攻击（带 target）。"
        )
        if snap.get("playable_blocks"):
            lines.append(
                f"  叠满防约+{snap['block_gain_if_all_blocks']} → "
                f"叠后净入伤≈{snap['projected_net_after_blocks']}"
            )
    elif snap.get("incoming") == 0:
        lines.append("  ✓ 无攻击意图：可输出，少堆无用防。")
    else:
        lines.append(f"  ✓ 净入伤{snap['net']} < HP：可规划输出，须用尽能量。")
    lines.append(
        "  card_index 以本次 get_state 手牌为准；sts2_act 若改你的 index 将**不执行**并退回。"
    )
    return "\n".join(lines)


def attach_survival_fields(payload: dict) -> dict:
    """Top-level keys on get_state for models that ignore play_brief."""
    if not isinstance(payload, dict):
        return payload
    st = str(payload.get("state_type") or "")
    if st not in ("monster", "elite", "boss", "hand_select"):
        return payload
    snap = survival_snapshot(payload)
    alert = survival_alert_line(payload)
    if alert:
        payload = dict(payload)
        payload["survival_alert"] = alert
        payload["survival_snapshot"] = snap
        try:
            from plugins.sts2.agent_contract import agent_sole_decider

            agent_only = agent_sole_decider()
        except Exception:
            agent_only = False
        pot_first = potion_required_before_play(payload)
        if pot_first:
            key = "coach_hint" if agent_only else "mandatory_next_action"
            payload[key] = pot_first
        elif snap.get("must_block_first") or snap.get("lethal_this_turn"):
            nxt = pick_survival_card(payload)
            if nxt:
                key = "coach_hint" if agent_only else "mandatory_next_action"
                payload[key] = nxt
    return payload
