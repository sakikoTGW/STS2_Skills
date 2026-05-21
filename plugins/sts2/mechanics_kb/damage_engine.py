"""Wiki-aligned attack/block damage engine (STS2 mechanics_kb)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from plugins.sts2.mechanics_kb.power_parse import (
    collect_powers,
    has_duration_debuff,
    relic_active,
)
from plugins.sts2.mechanics_kb.store import (
    get_card_debuff_table,
    get_multi_hit_patterns,
    get_multi_hit_table,
    get_power_entry,
    get_special_multipliers,
)


@dataclass
class DamageBreakdown:
    final: int = 0
    per_hit: int = 0
    hit_count: int = 1
    steps: list[str] = field(default_factory=list)
    multipliers: dict[str, float] = field(default_factory=dict)
    additive: int = 0
    warnings: list[str] = field(default_factory=list)

    def add_step(self, text: str) -> None:
        self.steps.append(text)


@dataclass
class DamageContext:
    card: dict
    player: dict
    enemy: dict | None = None
    state: dict | None = None
    player_powers: dict[str, int] | None = None
    enemy_powers: dict[str, int] | None = None
    vulnerable_turns_override: int | None = None
    skip_incoming_vuln: bool = False
    hit_index: int = 0
    hit_count: int | None = None
    cards_played_this_turn: int = 0
    attacks_played_this_turn: int = 0
    hit_from_behind: bool = False
    consume_vigor: bool = True
    is_hang_attack: bool = False


# ---------------------------------------------------------------------------
# Card parsing
# ---------------------------------------------------------------------------


def _card_base_damage(card: dict) -> int:
    for key in ("damage", "base_damage", "display_damage"):
        if card.get(key) is not None:
            try:
                return int(card[key])
            except (TypeError, ValueError):
                pass
    desc = str(card.get("description", "") or "")
    for pat in (r"(\d+)\s*点?伤害", r"deal\s+(\d+)", r"造成\s*(\d+)", r"(\d+)\s*damage"):
        m = re.search(pat, desc, re.I)
        if m:
            return int(m.group(1))
    return 0


def _is_attack(card: dict) -> bool:
    try:
        from plugins.sts2.combat_brain import _card_is_attack

        return _card_is_attack(card)
    except Exception:
        t = str(card.get("type", "") or "").lower()
        return "attack" in t or "攻击" in t


def _card_upgraded(card: dict) -> bool:
    cid = str(card.get("id", "")).upper()
    name = str(card.get("name", ""))
    return "+" in name or "UPGRADED" in cid or card.get("upgraded") is True


def _scaled(card: dict, key: str) -> int:
    row = get_card_debuff_table().get(str(card.get("id", "")).upper()) or {}
    vals = row.get(key)
    if not vals:
        return 0
    if isinstance(vals, list):
        return int(vals[1] if _card_upgraded(card) and len(vals) > 1 else vals[0])
    return 0


def card_applies_vulnerable_turns(card: dict) -> int:
    cid = str(card.get("id", "")).upper()
    v = _scaled(card, "vulnerable_turns")
    if v:
        return v
    if cid == "BASH" or "痛击" in str(card.get("name", "")):
        return 3 if _card_upgraded(card) else 2
    desc = str(card.get("description", "") or "")
    if "易伤" in desc or "vulnerable" in desc.lower():
        m = re.search(r"(\d+)\s*层?易伤", desc)
        return int(m.group(1)) if m else 2
    return 0


def card_applies_weak_turns(card: dict) -> int:
    v = _scaled(card, "weak_turns")
    if v:
        return v
    desc = str(card.get("description", "") or "")
    if "虚弱" in desc or "weak" in desc.lower():
        m = re.search(r"(\d+)\s*层?虚弱", desc)
        return int(m.group(1)) if m else 1
    return 0


def card_hit_count(card: dict, *, energy: int = 0) -> int:
    if card.get("hits") is not None:
        try:
            return max(1, int(card["hits"]))
        except (TypeError, ValueError):
            pass
    cid = str(card.get("id", "")).upper()
    row = get_multi_hit_table().get(cid) or {}
    if "hits" in row:
        hs = row["hits"]
        return int(hs[1] if _card_upgraded(card) and len(hs) > 1 else hs[0])
    if cid == "WHIRLWIND" or "WHIRL" in cid:
        int(row.get("base_per_hit", 5))
        return max(1, energy) if energy > 0 else 1
    desc = str(card.get("description", "") or "")
    for pat in get_multi_hit_patterns():
        m = re.search(pat.get("regex", ""), desc, re.I if pat.get("flags") else 0)
        if m:
            return max(1, int(m.group(int(pat.get("group", 1)))))
    return 1


def _enchant_additive(card: dict) -> int:
    bonus = 0
    for key in ("enchantments", "enchants", "mods"):
        raw = card.get(key)
        if not raw:
            continue
        items = raw if isinstance(raw, list) else [raw]
        for it in items:
            if isinstance(it, dict):
                blob = " ".join(str(it.get(k) or "") for k in ("id", "name", "type")).lower()
            else:
                blob = str(it).lower()
            if "sharp" in blob or "锋利" in blob:
                bonus += 2
            if "vigorous" in blob or "充沛" in blob:
                bonus += int(it.get("amount", 2)) if isinstance(it, dict) else 2
    return bonus


# ---------------------------------------------------------------------------
# Multipliers (wiki)
# ---------------------------------------------------------------------------


def _debilitate_doubles(holder_powers: dict[str, int]) -> bool:
    return has_duration_debuff(holder_powers, "DEBILITATE")


def vulnerable_multiplier(
    enemy_powers: dict[str, int],
    player: dict,
    *,
    turns_active: bool = True,
) -> float:
    if not turns_active and not has_duration_debuff(enemy_powers, "VULNERABLE"):
        return 1.0
    mult = float((get_power_entry("VULNERABLE") or {}).get("damage_multiplier") or 1.5)
    if relic_active(player, "PAPER_PHROG"):
        mult = max(mult, 1.75)
    if relic_active(player, "CRUELTY"):
        mult = max(mult, 1.75)
    if _debilitate_doubles(enemy_powers):
        mult *= 2.0
    return mult


def weak_multiplier(holder_powers: dict[str, int], player: dict) -> float:
    if not has_duration_debuff(holder_powers, "WEAK"):
        return 1.0
    mult = float((get_power_entry("WEAK") or {}).get("damage_multiplier") or 0.75)
    if relic_active(player, "PAPER_KRANE"):
        ent = get_power_entry("WEAK") or {}
        mult = float(ent.get("paper_krane_multiplier") or 0.6)
    if _debilitate_doubles(holder_powers):
        mult = 0.5
    return mult


def slow_multiplier(enemy_powers: dict[str, int], cards_played: int) -> float:
    stacks = int(enemy_powers.get("SLOW", 0) or 0)
    if stacks <= 0 or cards_played <= 0:
        return 1.0
    return 1.0 + 0.1 * stacks * cards_played


def incoming_special_multiplier(
    enemy_powers: dict[str, int],
    *,
    hit_from_behind: bool,
    is_hang_attack: bool,
) -> float:
    mult = 1.0
    if is_hang_attack:
        hang = int(enemy_powers.get("HANG", 0) or 0)
        if hang > 0:
            mult *= max(1.0, float(hang))
    if has_duration_debuff(enemy_powers, "SURROUNDED") and hit_from_behind:
        mult *= float((get_power_entry("SURROUNDED") or {}).get("damage_multiplier") or 1.5)
    flank = int(enemy_powers.get("FLANKING", 0) or 0)
    if flank > 0:
        mult *= float(2**min(flank, 8))
    knock = int(enemy_powers.get("KNOCKDOWN", 0) or 0)
    if knock > 0:
        mult *= max(1.0, float(knock))
    for ent in get_special_multipliers():
        mid = str(ent.get("id", "")).upper()
        if mid == "SURROUNDED" and hit_from_behind:
            mult *= float(ent.get("multiplier") or 1.5)
    return mult


def outgoing_special_multiplier(
    player_powers: dict[str, int],
    player: dict,
    *,
    attacks_played: int,
    pen_nib_triggers: bool = True,
) -> float:
    mult = 1.0
    if int(player_powers.get("SHRINK", 0) or 0) > 0:
        mult *= float((get_power_entry("SHRINK") or {}).get("damage_multiplier") or 0.7)
    if int(player_powers.get("DOUBLE_DAMAGE", 0) or 0) > 0:
        mult *= float((get_power_entry("DOUBLE_DAMAGE") or {}).get("damage_multiplier") or 2.0)
    for ent in get_special_multipliers():
        if str(ent.get("id")) == "DOUBLE_DAMAGE" and int(player_powers.get("DOUBLE_DAMAGE", 0) or 0) > 0:
            mult *= float(ent.get("multiplier") or 2.0)
    if pen_nib_triggers and relic_active(player, "PEN_NIB"):
        for r in get_special_multipliers():
            pass
        # 第 10、20… 次攻击牌双倍
        if (attacks_played + 1) % 10 == 0:
            mult *= 2.0
    return mult


# ---------------------------------------------------------------------------
# Per-hit pipeline
# ---------------------------------------------------------------------------


def _additive_per_hit(card: dict, player_powers: dict[str, int], player: dict) -> int:
    base = _card_base_damage(card)
    strength = int(player_powers.get("STRENGTH", 0) or 0)
    accuracy = int(player_powers.get("ACCURACY", 0) or 0)
    vigor = int(player_powers.get("VIGOR", 0) or 0)
    enchant = _enchant_additive(card)
    strike_bonus = 0
    if relic_active(player, "STRIKE_DUMMY") and "STRIKE" in str(card.get("id", "")).upper():
        strike_bonus = 1
    return base + strength + accuracy + vigor + enchant + strike_bonus


def compute_single_hit(ctx: DamageContext) -> DamageBreakdown:
    bd = DamageBreakdown()
    card, player = ctx.card, ctx.player
    if not _is_attack(card):
        bd.warnings.append("非攻击牌")
        return bd

    p_powers = ctx.player_powers if ctx.player_powers is not None else collect_powers(player)
    e_powers = (
        ctx.enemy_powers
        if ctx.enemy_powers is not None
        else collect_powers(ctx.enemy or {})
    )

    base = _card_base_damage(card)
    favored_mult = 1.0
    if int(p_powers.get("FAVORED", 0) or 0) > 0:
        favored_mult = float((get_power_entry("FAVORED") or {}).get("damage_multiplier") or 2.0)

    # wiki: (base * favored) + strength + ...
    strength = int(p_powers.get("STRENGTH", 0) or 0)
    accuracy = int(p_powers.get("ACCURACY", 0) or 0)
    vigor = int(p_powers.get("VIGOR", 0) or 0) if ctx.consume_vigor else 0
    enchant = _enchant_additive(card)
    strike_bonus = 1 if relic_active(player, "STRIKE_DUMMY") and "STRIKE" in str(card.get("id", "")).upper() else 0

    pre = float(base) * favored_mult
    if favored_mult != 1.0:
        bd.add_step(f"眷顾: 牌面{base}×{favored_mult}")
    additive_rest = strength + accuracy + vigor + enchant + strike_bonus
    value = pre + additive_rest
    bd.additive = int(value)
    bd.add_step(
        f"加算: {f'{pre:.0f}'}+{additive_rest}"
        f"(力{strength}准{accuracy}活{vigor}附{enchant})"
    )

    om = weak_multiplier(p_powers, player)
    if om != 1.0:
        value *= om
        bd.multipliers["weak"] = om
        bd.add_step(f"×虚弱({om:.2f})")

    om = outgoing_special_multiplier(
        p_powers,
        player,
        attacks_played=ctx.attacks_played_this_turn,
    )
    if om != 1.0:
        value *= om
        bd.multipliers["outgoing"] = om
        bd.add_step(f"×攻击方({om:.2f})")

    apply_vuln = not ctx.skip_incoming_vuln and card_applies_vulnerable_turns(card) == 0
    vuln_on = False
    if apply_vuln:
        if ctx.vulnerable_turns_override is not None:
            vuln_on = int(ctx.vulnerable_turns_override) > 0
        else:
            vuln_on = has_duration_debuff(e_powers, "VULNERABLE")
        if vuln_on:
            vm = vulnerable_multiplier(
                e_powers if has_duration_debuff(e_powers, "VULNERABLE") else {"VULNERABLE": 1},
                player,
                turns_active=True,
            )
            value *= vm
            bd.multipliers["vulnerable"] = vm
            bd.add_step(f"×易伤({vm:.2f})")

    sm = slow_multiplier(e_powers, ctx.cards_played_this_turn)
    if sm != 1.0:
        value *= sm
        bd.multipliers["slow"] = sm
        bd.add_step(f"×缓慢({sm:.2f})")

    im = incoming_special_multiplier(
        e_powers,
        hit_from_behind=ctx.hit_from_behind,
        is_hang_attack=ctx.is_hang_attack,
    )
    if im != 1.0:
        value *= im
        bd.multipliers["incoming_special"] = im
        bd.add_step(f"×受击特殊({im:.2f})")

    bd.per_hit = max(0, int(math.floor(value)))
    bd.add_step(f"→ floor/段 = {bd.per_hit}")
    return bd


def compute_attack_damage(ctx: DamageContext) -> DamageBreakdown:
    from plugins.sts2.mechanics_kb.context import merge_context_into_damage_ctx

    merge_context_into_damage_ctx(ctx, ctx.state)

    if ctx.skip_incoming_vuln or card_applies_vulnerable_turns(ctx.card) > 0:
        pass

    try:
        energy = int((ctx.player or {}).get("energy", 0) or 0)
    except (TypeError, ValueError):
        energy = 0
    hits = ctx.hit_count if ctx.hit_count is not None else card_hit_count(ctx.card, energy=energy)
    hits = max(1, hits)

    total_bd = DamageBreakdown(hit_count=hits)
    total = 0
    for h in range(hits):
        sub = compute_single_hit(
            DamageContext(
                card=ctx.card,
                player=ctx.player,
                enemy=ctx.enemy,
                state=ctx.state,
                player_powers=ctx.player_powers,
                enemy_powers=ctx.enemy_powers,
                vulnerable_turns_override=ctx.vulnerable_turns_override,
                skip_incoming_vuln=ctx.skip_incoming_vuln,
                hit_index=h,
                hit_count=hits,
                cards_played_this_turn=ctx.cards_played_this_turn,
                attacks_played_this_turn=ctx.attacks_played_this_turn,
                hit_from_behind=ctx.hit_from_behind,
                consume_vigor=ctx.consume_vigor and h == 0,
                is_hang_attack=ctx.is_hang_attack,
            )
        )
        total += sub.per_hit
        if h == 0:
            total_bd.steps = sub.steps.copy()
        elif hits > 1:
            total_bd.add_step(f"  段{h + 1}≈{sub.per_hit}")
    total_bd.per_hit = total_bd.final = total
    if hits > 1:
        total_bd.add_step(f"×{hits}段合计={total}")
    return total_bd


# Back-compat aliases
_vulnerable_multiplier = vulnerable_multiplier
_card_applies_vulnerable_turns = card_applies_vulnerable_turns


def compute_block_from_card(
    card: dict,
    player: dict,
    *,
    player_powers: dict[str, int] | None = None,
) -> int:
    base = 0
    for key in ("block", "base_block", "display_block"):
        if card.get(key) is not None:
            try:
                base = int(card[key])
                break
            except (TypeError, ValueError):
                pass
    if base <= 0:
        desc = str(card.get("description", "") or "")
        m = re.search(r"(\d+)\s*点?格挡|(\d+)\s*block|获得\s*(\d+)", desc, re.I)
        if m:
            base = int(next(g for g in m.groups() if g))
    pp = player_powers if player_powers is not None else collect_powers(player)
    dex = int(pp.get("DEXTERITY", 0) or 0)
    fasten = int(pp.get("FASTEN", 0) or 0)
    raw = float(base + dex + fasten)
    if has_duration_debuff(pp, "FRAIL"):
        raw *= float((get_power_entry("FRAIL") or {}).get("block_multiplier") or 0.75)
    for bid in ("UNMOVABLE", "SHADOWMELD"):
        if int(pp.get(bid, 0) or 0) > 0:
            ent = get_power_entry(bid) or {}
            raw *= float(ent.get("block_multiplier") or 2.0)
    return max(0, int(math.floor(raw)))


def estimate_poison_tick(enemy: dict, player: dict | None = None) -> int:
    """下回合初中毒伤害（不经攻击管道）。"""
    ep = collect_powers(enemy)
    stacks = int(ep.get("POISON", 0) or 0)
    if stacks <= 0:
        return 0
    if relic_active(player or {}, "SNECKO_SKULL"):
        pass
    return stacks


def projected_vulnerable_turns(
    state: dict, hand: list, card: dict, *, enemy: dict | None = None
) -> int:
    from plugins.sts2.combat_brain import focus_enemy

    target = enemy or focus_enemy(state)
    if not target:
        return 0
    turns = 0
    ep = collect_powers(target)
    if has_duration_debuff(ep, "VULNERABLE"):
        turns = int(ep.get("VULNERABLE", 1))
    try:
        my_idx = int(card.get("index", 0))
    except (TypeError, ValueError):
        my_idx = 0
    for c in hand or []:
        if not isinstance(c, dict):
            continue
        try:
            idx = int(c.get("index", 0))
        except (TypeError, ValueError):
            continue
        if idx >= my_idx:
            continue
        turns += card_applies_vulnerable_turns(c)
    return turns
