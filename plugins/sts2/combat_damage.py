"""STS2 combat damage — API over mechanics_kb (full wiki pipeline)."""

from __future__ import annotations

from plugins.sts2.mechanics_kb.damage_engine import (
    DamageContext,
    card_applies_vulnerable_turns,
    compute_block_from_card,
    estimate_poison_tick,
    projected_vulnerable_turns,
)
from plugins.sts2.mechanics_kb.damage_engine import (
    compute_attack_damage as _kb_compute,
)
from plugins.sts2.mechanics_kb.damage_engine import (
    vulnerable_multiplier as _vulnerable_multiplier,
)
from plugins.sts2.mechanics_kb.power_parse import collect_powers, has_duration_debuff


def vulnerable_turns(enemy: dict) -> int:
    ep = collect_powers(enemy)
    return int(ep.get("VULNERABLE", 0) or 0) if has_duration_debuff(ep, "VULNERABLE") else 0


def vulnerable_damage_multiplier(
    enemy: dict,
    *,
    player: dict | None = None,
    state: dict | None = None,
) -> float:
    pl = player or (state or {}).get("player") or {}
    ep = collect_powers(enemy if enemy else {})
    if not has_duration_debuff(ep, "VULNERABLE") and isinstance(enemy, dict) and enemy.get("vulnerable"):
        ep = {**ep, "VULNERABLE": int(enemy.get("vulnerable", 1))}
    return _vulnerable_multiplier(ep, pl, turns_active=True)


def estimate_attack_damage(
    card: dict,
    player: dict,
    *,
    state: dict | None = None,
    enemy: dict | None = None,
    vulnerable_turns_when_hit: int | None = None,
    apply_vulnerable: bool = True,
) -> int:
    skip = card_applies_vulnerable_turns(card) > 0
    turns = vulnerable_turns_when_hit
    if apply_vulnerable and turns is None and enemy is not None:
        turns = vulnerable_turns(enemy)
    if apply_vulnerable and turns is None and state is not None:
        hand = list(player.get("hand") or [])
        from plugins.sts2.combat_brain import focus_enemy

        turns = projected_vulnerable_turns(state, hand, card, enemy=enemy or focus_enemy(state))
    bd = _kb_compute(
        DamageContext(
            card=card,
            player=player,
            enemy=enemy,
            state=state,
            vulnerable_turns_override=turns if apply_vulnerable else 0,
            skip_incoming_vuln=skip or not apply_vulnerable,
        )
    )
    return bd.final


projected_vulnerable_turns_after_prior_cards = projected_vulnerable_turns


def format_attack_damage_hint(card: dict, player: dict, state: dict) -> str:
    from plugins.sts2.combat_brain import _card_is_attack, focus_enemy

    if not _card_is_attack(card):
        return ""
    hand = list(player.get("hand") or [])
    applies = card_applies_vulnerable_turns(card)
    base = estimate_attack_damage(card, player, state=state, apply_vulnerable=False)
    if applies:
        return f"伤害≈{base} +易伤{applies}回合"
    turns = projected_vulnerable_turns(state, hand, card)
    full = estimate_attack_damage(
        card, player, state=state, enemy=focus_enemy(state), vulnerable_turns_when_hit=turns
    )
    if turns > 0 and full != base:
        mult = vulnerable_damage_multiplier(
            focus_enemy(state) or {"vulnerable": turns}, player=player, state=state
        )
        return f"伤害≈{full}(floor(({base})×{mult:.2f})·易伤{turns}回合)"
    return f"伤害≈{full}"


def format_hand_damage_ledger(state: dict) -> str:
    from plugins.sts2.mechanics_kb.brief import format_combat_mechanics_brief

    return format_combat_mechanics_brief(state)


__all__ = [
    "vulnerable_turns",
    "vulnerable_damage_multiplier",
    "card_applies_vulnerable_turns",
    "estimate_attack_damage",
    "projected_vulnerable_turns_after_prior_cards",
    "format_attack_damage_hint",
    "format_hand_damage_ledger",
    "compute_block_from_card",
    "estimate_poison_tick",
]
