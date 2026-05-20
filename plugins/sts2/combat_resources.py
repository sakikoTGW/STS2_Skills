"""Potions, Bloodletting, and other resource plays (shared by rules + LLM guard)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from plugins.sts2.combat_brain import (
    _affordable,
    _cost,
    _play_card,
    _target_entity_id,
    combat_should_wait,
    incoming_attack_damage,
    net_incoming_damage,
)


def _player_stats(state: dict) -> tuple[int, int, int, int, int, int]:
    player = state.get("player") or {}
    try:
        hp = int(player.get("hp", player.get("current_hp", 1)))
        max_hp = int(player.get("max_hp", hp) or hp or 1)
        block = int(player.get("block", 0))
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        hp, max_hp, block, energy = 1, 1, 0, 0
    enemies = (state.get("battle") or {}).get("enemies") or []
    incoming = incoming_attack_damage(enemies)
    net = net_incoming_damage(incoming, block)
    return hp, max_hp, block, energy, incoming, net


def _potion_usable(pot: dict) -> bool:
    if not pot:
        return False
    if pot.get("can_use_in_combat") is False:
        return False
    return True


def prefer_potion_play(state: dict) -> Optional[dict]:
    """Use potions when they save the run or unlock a turn (energy)."""
    if combat_should_wait(state):
        return None
    try:
        from plugins.sts2.autoplay import get_controller

        if get_controller()._potion_fail_streak >= 2:  # noqa: SLF001
            return None
    except Exception:
        pass
    player = state.get("player") or {}
    hp, max_hp, block, energy, incoming, net = _player_stats(state)
    pots = player.get("potions") or []
    if not any(pots):
        return None
    target = _target_entity_id((state.get("battle") or {}).get("enemies") or [])
    hand = player.get("hand") or []

    _energy_draw_hints = (
        "energy",
        "能量",
        "draw",
        "抽",
        "card",
        "牌",
        "痊愈",
        "cure",
        "regen",
        "恢复",
    )

    # Lethal this hit — heal/block/energy potions (energy before blocks fail)
    if net >= hp and hp > 0:
        hand_blocks = 0
        try:
            from plugins.sts2.combat_brain import _card_is_block, estimate_block_gain

            for c in hand:
                if c.get("can_play") and _card_is_block(c):
                    hand_blocks += estimate_block_gain(c)
        except Exception:
            pass
        projected_net = net_incoming_damage(incoming, block + hand_blocks)
        need_energy = projected_net >= hp and energy <= 2

        if need_energy:
            for slot, pot in enumerate(pots):
                if not _potion_usable(pot):
                    continue
                blob = (
                    str(pot.get("description", ""))
                    + str(pot.get("name", ""))
                    + str(pot.get("id", ""))
                ).lower()
                if any(k in blob for k in _energy_draw_hints):
                    return {"action": "use_potion", "slot": slot}

        for slot, pot in enumerate(pots):
            if not _potion_usable(pot):
                continue
            blob = (
                str(pot.get("description", ""))
                + str(pot.get("name", ""))
                + str(pot.get("id", ""))
            ).lower()
            if any(k in blob for k in ("block", "格挡", "heal", "治疗", "生命", "hp")):
                body: Dict[str, Any] = {"action": "use_potion", "slot": slot}
                if target and any(
                    k in blob for k in ("enemy", "敌人", "weak", "虚弱", "fire", "火")
                ):
                    body["target"] = target
                return body

    # Low HP under real attack — debuff / weak potions
    if hp < max_hp * 0.45 and incoming > block and incoming >= 6:
        for slot, pot in enumerate(pots):
            if not _potion_usable(pot):
                continue
            blob = (
                str(pot.get("description", ""))
                + str(pot.get("name", ""))
                + str(pot.get("id", ""))
            ).lower()
            if target and any(
                k in blob for k in ("weak", "虚弱", "vulnerable", "易伤", "fire", "火", "enemy")
            ):
                return {"action": "use_potion", "slot": slot, "target": target}

    # Energy potion — hand has playable-in-principle cards but not enough energy
    unplayable_cost = [
        c
        for c in hand
        if c.get("can_play") is False
        and str(c.get("unplayable_reason", "")).lower() in ("energycosttoohigh", "")
        and _cost(c) > energy
    ]
    if energy <= 1 and unplayable_cost:
        for slot, pot in enumerate(pots):
            if not _potion_usable(pot):
                continue
            blob = (
                str(pot.get("description", ""))
                + str(pot.get("name", ""))
                + str(pot.get("id", ""))
            ).lower()
            if "energy" in blob or "能量" in blob or pot.get("id") == "ENERGY_POTION":
                return {"action": "use_potion", "slot": slot}

    return None


def prefer_bloodletting_play(state: dict) -> Optional[dict]:
    """0-cost 放血 when HP buffer exists and we need energy."""
    if combat_should_wait(state):
        return None
    player = state.get("player") or {}
    hp, max_hp, block, energy, incoming, net = _player_stats(state)
    if hp <= max(10, max_hp // 6):
        return None
    if net >= hp - 4:
        return None
    hand = player.get("hand") or []
    playable = _affordable(hand, energy)
    bleed_cost_hp = 3
    for c in playable:
        cid = str(c.get("id", "")).upper()
        name = str(c.get("name", ""))
        if cid != "BLOODLETTING" and name != "放血":
            continue
        desc = str(c.get("description", ""))
        m = re.search(r"失去\s*(\d+)\s*点?生命|lose\s+(\d+)\s+hp", desc, re.I)
        if m:
            bleed_cost_hp = int(m.group(1) or m.group(2) or 3)
        if hp <= bleed_cost_hp + 5:
            continue
        if net >= max(0, hp - bleed_cost_hp):
            continue
        needs_energy = energy <= 1 or any(
            _cost(x) > energy for x in hand if x.get("index") != c.get("index")
        )
        if not needs_energy and energy >= 2:
            continue
        target = _target_entity_id((state.get("battle") or {}).get("enemies") or [])
        return _play_card(c, target)
    return None
