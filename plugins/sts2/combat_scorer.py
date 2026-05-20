"""Score every legal combat action and pick the best — easier to tune than if-else chains."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from plugins.sts2.combat_brain import (
    _affordable,
    _card_is_attack,
    _card_is_block,
    _card_is_power,
    _cost,
    _play_card,
    _run_floor,
    _target_entity_id,
    combat_should_end_turn,
    combat_should_wait,
    incoming_attack_damage,
    is_safe_from_incoming,
    try_lethal_attack,
)

Action = Dict[str, Any]


def _lessons_text(state: dict) -> str:
    try:
        from plugins.sts2.lessons import lessons_for_combat

        return " ".join(lessons_for_combat(state)).lower()
    except Exception:
        return ""


def _score_end_turn(
    *,
    energy: int,
    playable: list,
    incoming: int,
    block: int,
    hp: int,
    best_attack_score: float,
    best_block_score: float,
) -> float:
    if energy <= 0:
        return 80.0
    if not playable:
        return 70.0
    gap = incoming - block
    if gap >= hp and best_block_score > 5:
        return -120.0
    if gap > 0 and best_block_score > best_attack_score + 5:
        return -60.0
    # Don't end with attacks left when safe
    if incoming <= block and best_attack_score > 15:
        return -100.0
    if best_block_score > best_attack_score + 10 and incoming > block:
        return 5.0
    if energy >= 2 and best_attack_score < 10:
        return -40.0
    return 10.0


def _card_is_draw_or_cycle(card: dict) -> bool:
    """Draw / exhaust-cycle skills — spend energy before end_turn."""
    desc = str(card.get("description", "")).lower()
    name = str(card.get("name", "")).lower()
    cid = str(card.get("id", "")).upper()
    if any(k in desc for k in ("draw", "抽", "张牌", "exhaust", "消耗")):
        if "draw" in desc or "抽" in desc or "张牌" in desc:
            return True
    if any(k in name for k in ("契约", "contract", "专注", "trance", "耸肩", "祭品", "offering")):
        return True
    if any(k in cid for k in ("OFFERING", "BATTLE_TRANCE", "DARK_EMBRACE", "BRUTALITY", "BURNING_PACT")):
        return True
    return False


def _score_card(
    card: dict,
    *,
    incoming: int,
    block: int,
    hp: int,
    max_hp: int,
    energy: int,
    floor: int,
    lessons: str,
    danger_mult: float = 1.0,
) -> float:
    score = 0.0
    cid = str(card.get("id", "")).upper()
    cost = _cost(card)

    if _card_is_power(card):
        score += 45.0 + (10 - cost) * 3
        if floor <= 6:
            score += 15.0

    if _card_is_attack(card):
        score += 35.0 + cost * 4
        if incoming <= block:
            score += 45.0
        elif is_safe_from_incoming(incoming, block, hp):
            score += 55.0
        elif incoming <= block + 3:
            score += 15.0
        else:
            score -= 10.0
        if "bash" in cid.lower() or "vulnerable" in str(card.get("description", "")).lower():
            score += 12.0

    if _card_is_block(card):
        score += 20.0
        if is_safe_from_incoming(incoming, block, hp):
            score -= 200.0
        gap = incoming - block
        if gap > 0:
            score += gap * 9.0 * danger_mult
        else:
            score -= 35.0
        if incoming == 0:
            score -= 60.0
        if "阵亡" in lessons or "格挡" in lessons:
            if gap > 0:
                score += 12.0 * danger_mult

    if hp < max_hp * 0.4 and _card_is_block(card) and incoming > 0:
        score += 25.0 * danger_mult
    threat_gap = incoming - block
    if threat_gap >= hp and _card_is_block(card):
        score += 40.0 * danger_mult

    if cost == 0:
        score += 25.0

    if _card_is_draw_or_cycle(card):
        score += 42.0
        if energy >= cost and incoming > block:
            score += 28.0

    if not card.get("can_play", False):
        return -999.0
    if cost > energy:
        return -999.0

    try:
        from plugins.sts2.knowledge import combat_card_bonus

        score += combat_card_bonus(cid)
    except Exception:
        pass

    return score


def decide_combat_scored(state: dict) -> Action:
    """Pick highest-scoring legal action."""
    if combat_should_wait(state):
        return {"action": "__wait__"}
    if combat_should_end_turn(state):
        return {"action": "end_turn"}

    battle = state.get("battle") or {}

    player = state.get("player") or {}
    hand = player.get("hand") or []
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    try:
        hp = int(player.get("hp", player.get("current_hp", 1)))
        max_hp = int(player.get("max_hp", hp) or hp or 1)
    except (TypeError, ValueError):
        hp, max_hp = 1, 1
    try:
        block = int(player.get("block", 0))
    except (TypeError, ValueError):
        block = 0

    enemies = battle.get("enemies") or []
    target = _target_entity_id(enemies)
    incoming = incoming_attack_damage(enemies)
    playable = _affordable(hand, energy)
    floor = _run_floor(state)
    lessons = _lessons_text(state)
    try:
        from plugins.sts2.act1_clear import combat_danger_multiplier

        danger_mult = combat_danger_multiplier(state)
    except Exception:
        danger_mult = 1.0

    if not hand and energy > 0 and not playable:
        return {"action": "__wait__"}

    lethal = try_lethal_attack(state)
    if lethal:
        return lethal

    from plugins.sts2.combat_brain import prefer_block_play
    from plugins.sts2.combat_resources import prefer_bloodletting_play, prefer_potion_play

    potion = prefer_potion_play(state)
    if potion:
        return potion
    bleed = prefer_bloodletting_play(state)
    if bleed:
        return bleed

    urgent_block = prefer_block_play(state)
    if urgent_block:
        return urgent_block

    candidates: List[Tuple[Action, float]] = []
    best_atk = -999.0
    best_blk = -999.0

    for card in playable:
        sc = _score_card(
            card,
            incoming=incoming,
            block=block,
            hp=hp,
            max_hp=max_hp,
            energy=energy,
            floor=floor,
            lessons=lessons,
            danger_mult=danger_mult,
        )
        if _card_is_attack(card):
            best_atk = max(best_atk, sc)
        if _card_is_block(card):
            best_blk = max(best_blk, sc)
        if sc > -500:
            candidates.append((_play_card(card, target), sc))

    et_sc = _score_end_turn(
        energy=energy,
        playable=playable,
        incoming=incoming,
        block=block,
        hp=hp,
        best_attack_score=best_atk,
        best_block_score=best_blk,
    )
    candidates.append(({"action": "end_turn"}, et_sc))

    if not candidates:
        return {"action": "end_turn"}

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]
