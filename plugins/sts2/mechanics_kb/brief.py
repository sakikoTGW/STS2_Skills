"""Format mechanics KB + live state for agent / play_brief."""

from __future__ import annotations

from typing import Any

from plugins.sts2.mechanics_kb.damage_engine import (
    DamageContext,
    card_applies_vulnerable_turns,
    card_hit_count,
    compute_attack_damage,
    compute_block_from_card,
    estimate_poison_tick,
    projected_vulnerable_turns,
)
from plugins.sts2.mechanics_kb.power_parse import collect_powers
from plugins.sts2.mechanics_kb.store import get_pipeline, kb_version, lookup_wiki_examples


def format_combat_mechanics_brief(state: dict) -> str:
    if str(state.get("state_type") or "").lower() not in ("monster", "combat", "battle"):
        return ""

    lines: list[str] = [
        f"【机制知识库 v{kb_version()}·wiki.gg 全管道】",
        "Duration 易伤/虚弱/脆弱: 层数=回合，倍率固定(×1.5/×0.75/格挡×0.75)",
        "Intensity 力量/毒/缓慢: 层数=强度 | 攻击: 眷顾→加算→攻方乘算→受击乘算→floor",
        "非攻击伤害(毒/直扣HP)不走本管道",
    ]
    pipe = get_pipeline()
    phases = (pipe.get("attack_per_hit") or {}).get("phases") or []
    if phases:
        lines.append("管道: " + " → ".join(p.get("label", "") for p in phases))

    player = state.get("player") or {}
    pp = collect_powers(player)
    if pp:
        lines.append("玩家: " + ", ".join(f"{k}{v}" for k, v in sorted(pp.items()) if v))

    from plugins.sts2.combat_brain import _card_is_attack, focus_enemy

    focus = focus_enemy(state)
    if focus:
        ep = collect_powers(focus)
        poison = estimate_poison_tick(focus, player)
        lines.append(
            f"集火 {focus.get('name')} HP{focus.get('hp')} "
            + ", ".join(f"{k}{v}" for k, v in sorted(ep.items()) if v)
            + (f" | 下回合毒{poison}" if poison else "")
        )

    hand = list(player.get("hand") or [])
    for c in sorted(hand, key=lambda x: int(x.get("index", 0) or 0)):
        if not _card_is_attack(c):
            blk = c.get("block")
            if blk or "格挡" in str(c.get("description", "")):
                lines.append(
                    f"  [{c.get('index')}] {c.get('name')}: 格挡≈{compute_block_from_card(c, player)}"
                )
            continue
        hits = card_hit_count(c, energy=int(player.get("energy", 0) or 0))
        skip = card_applies_vulnerable_turns(c) > 0
        turns = 0 if skip else projected_vulnerable_turns(state, hand, c, enemy=focus)
        bd = compute_attack_damage(
            DamageContext(
                card=c,
                player=player,
                enemy=focus,
                state=state,
                vulnerable_turns_override=turns,
                skip_incoming_vuln=skip,
            )
        )
        extra = ""
        if card_applies_vulnerable_turns(c):
            extra = f" +易伤{card_applies_vulnerable_turns(c)}回合"
        elif hits > 1:
            extra = f" {hits}段"
        lines.append(
            f"  [{c.get('index')}] {c.get('name')}: ≈{bd.final}{extra} | "
            + " → ".join(bd.steps[-4:])
        )

    bash = next((c for c in hand if card_applies_vulnerable_turns(c) > 0), None)
    strikes = [
        c
        for c in hand
        if _card_is_attack(c)
        and not card_applies_vulnerable_turns(c)
        and "STRIKE" in str(c.get("id", "")).upper()
    ]
    if bash and strikes and focus:
        bd = compute_attack_damage(
            DamageContext(
                card=strikes[0],
                player=player,
                enemy=focus,
                state=state,
                vulnerable_turns_override=projected_vulnerable_turns(
                    state, hand, strikes[0], enemy=focus
                ),
            )
        )
        lines.append(f"  ★ 先{bash.get('name')}再{strikes[0].get('name')}: ≈{bd.final}")

    return "\n".join(lines)


def validate_wiki_examples() -> list[dict[str, Any]]:
    results = []
    for ex in lookup_wiki_examples():
        name = ex.get("name", "?")
        if "expected_block" in ex:
            player: dict = {"powers": []}
            if ex.get("dexterity"):
                player["powers"] = [{"name": "Dexterity", "amount": ex["dexterity"]}]
            if ex.get("frail"):
                player["powers"].append({"name": "Frail", "amount": 1})
            got = compute_block_from_card({"block": ex.get("card_base_block", 0)}, player)
            results.append(
                {"name": name, "expected": ex["expected_block"], "got": got, "ok": got == ex["expected_block"]}
            )
            continue
        player = {"powers": [], "relics": []}
        if ex.get("strength"):
            player["strength"] = ex["strength"]
        enemy = {}
        if ex.get("vulnerable"):
            enemy = {"powers": [{"name": "Vulnerable", "amount": 1}]}
        if ex.get("weak_on_attacker"):
            player["powers"] = [{"name": "Weak", "amount": 1}]
        if ex.get("debilitate_on_attacker"):
            player["powers"].append({"name": "Debilitate", "amount": 1})
        if ex.get("slow_stacks"):
            enemy = enemy or {}
            enemy.setdefault("powers", []).append({"name": "Slow", "amount": ex["slow_stacks"]})
        card = {"damage": ex.get("card_base", 0), "type": "attack", "id": "STRIKE"}
        if ex.get("hits"):
            card["id"] = "TWIN_STRIKE"
        bd = compute_attack_damage(
            DamageContext(
                card=card,
                player=player,
                enemy=enemy or None,
                cards_played_this_turn=int(ex.get("cards_played", 0) or 0),
                hit_count=int(ex.get("hits", 0) or 0) or None,
            )
        )
        results.append(
            {
                "name": name,
                "expected": ex["expected"],
                "got": bd.final,
                "ok": bd.final == ex["expected"],
                "steps": bd.steps,
            }
        )
    return results
