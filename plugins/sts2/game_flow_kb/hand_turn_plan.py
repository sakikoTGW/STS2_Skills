"""Plan entire hand for current combat turn — not single-card hints."""

from __future__ import annotations

from plugins.sts2.mechanics_kb.context import combat_runtime
from plugins.sts2.mechanics_kb.damage_engine import (
    DamageContext,
    card_applies_vulnerable_turns,
    compute_attack_damage,
    compute_block_from_card,
)


def _cost(card: dict) -> int:
    raw = str(card.get("cost", "99")).upper()
    if raw == "X":
        return 99
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 99


def _card_is_block(card: dict) -> bool:
    try:
        from plugins.sts2.combat_brain import _card_is_block

        return _card_is_block(card)
    except Exception:
        return bool(card.get("block"))


def _card_is_attack(card: dict) -> bool:
    try:
        from plugins.sts2.combat_brain import _card_is_attack

        return _card_is_attack(card)
    except Exception:
        return "attack" in str(card.get("type", "")).lower()


def format_hand_turn_plan(state: dict) -> str:
    st = str(state.get("state_type") or "").lower()
    if st not in ("monster", "elite", "boss", "hand_select", "combat", "battle"):
        return ""

    player = state.get("player") or {}
    hand = [c for c in (player.get("hand") or []) if isinstance(c, dict)]
    if not hand:
        return ""

    try:
        energy = int(player.get("energy", 0) or 0)
    except (TypeError, ValueError):
        energy = 0

    from plugins.sts2.combat_brain import focus_enemy

    focus = focus_enemy(state)
    rt = combat_runtime(state)
    cards_played = int(rt.get("cards_played_this_turn") or 0)
    attacks_played = int(rt.get("attacks_played_this_turn") or 0)

    playable = sorted(
        [
            c
            for c in hand
            if c.get("can_play", True) and _cost(c) <= energy
        ],
        key=lambda x: int(x.get("index", 0) or 0),
    )
    if not playable:
        return "【本回合手牌计划】无可用牌"

    vuln_cards = [c for c in playable if card_applies_vulnerable_turns(c) > 0]
    atk_cards = [
        c
        for c in playable
        if _card_is_attack(c) and not card_applies_vulnerable_turns(c)
    ]
    blk_cards = [c for c in playable if _card_is_block(c)]
    other = [
        c for c in playable if c not in vuln_cards and c not in atk_cards and c not in blk_cards
    ]

    atk_cards.sort(
        key=lambda c: -compute_attack_damage(
            DamageContext(card=c, player=player, enemy=focus, state=state)
        ).final,
    )

    priority = vuln_cards + atk_cards + blk_cards + other

    lines = [
        "【本回合手牌计划·全手牌】模拟按 index 优先：先上易伤→高伤攻击→格挡",
        f"  能量{energy} | 本回合已出牌{cards_played} | 已攻击{attacks_played}次",
    ]

    rem = energy
    projected_vuln = 0
    if focus:
        from plugins.sts2.mechanics_kb.power_parse import collect_powers, has_duration_debuff

        ep = collect_powers(focus)
        if has_duration_debuff(ep, "VULNERABLE"):
            projected_vuln = int(ep.get("VULNERABLE", 1))

    total_dmg = 0
    total_blk = 0
    played_n = 0
    atk_n = attacks_played

    for c in priority:
        cost = _cost(c)
        if cost > rem:
            continue
        rem -= cost
        played_n += 1
        skip_v = card_applies_vulnerable_turns(c) > 0
        if _card_is_attack(c):
            atk_n += 1
            bd = compute_attack_damage(
                DamageContext(
                    card=c,
                    player=player,
                    enemy=focus,
                    state=state,
                    vulnerable_turns_override=projected_vuln if not skip_v else 0,
                    skip_incoming_vuln=skip_v,
                    cards_played_this_turn=cards_played + played_n - 1,
                    attacks_played_this_turn=atk_n - 1,
                )
            )
            total_dmg += bd.final
            if skip_v:
                projected_vuln = max(projected_vuln, card_applies_vulnerable_turns(c))
            tag = f"≈{bd.final}" + (f"×{bd.hit_count}段" if bd.hit_count > 1 else "")
        elif _card_is_block(c):
            b = compute_block_from_card(c, player)
            total_blk += b
            tag = f"格挡≈{b}"
        else:
            tag = "技能"
        lines.append(f"  {played_n}) [{c.get('index')}] {c.get('name')} 费{cost} → {tag}")

    if played_n < len(playable):
        left = [c for c in priority if _cost(c) > rem or c not in priority[:played_n]]
        if left:
            lines.append(
                "  费不够未模拟: "
                + ", ".join(f"[{c.get('index')}]{c.get('name')}" for c in left[:4])
            )

    lines.append(f"  合计伤害≈{total_dmg} 格挡≈{total_blk} 剩能{rem}")
    if projected_vuln:
        lines.append(f"  打完易伤≈{projected_vuln}回合")
    return "\n".join(lines)
