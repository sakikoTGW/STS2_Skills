"""Turn-level play sequencing: combo damage, damage caps (hardened shell), battle budget."""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from plugins.sts2.combat_brain import (
    _card_is_attack,
    _card_is_block,
    _cost,
    card_applies_vulnerable,
    enemy_vulnerable_stacks,
    estimate_block_gain,
    estimate_card_damage,
    incoming_attack_damage,
    vulnerable_damage_multiplier,
)

_MECH_PATH = Path(__file__).resolve().parent / "references" / "enemy_mechanics.json"
_VULN_IDS = frozenset(
    {
        "BASH",
        "POMMEL_STRIKE",
        "THUNDERCLAP",
        "SHOCKWAVE",
        "SETUP_STRIKE",
        "BREAKTHROUGH",
    }
)
_AOE_IDS = frozenset(
    {
        "CLEAVE",
        "WHIRLWIND",
        "BREAKTHROUGH",
        "THUNDERCLAP",
        "SHOCKWAVE",
        "INCINERATE",
        "COMBUSTION",
        "IMMOLATE",
    }
)


@lru_cache(maxsize=1)
def _mech_catalog() -> dict:
    try:
        return json.loads(_MECH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"power_patterns": [], "enemies": {}}


@dataclass
class EnemyMech:
    entity_id: str
    name: str
    hp: int
    block: int = 0
    vuln_stacks: int = 0
    damage_cap_per_turn: int | None = None
    damage_taken_this_turn: int = 0
    notes: str = ""


@dataclass
class PlanState:
    energy: int
    player_block: int
    hand: list[dict]
    enemies: list[EnemyMech]
    player: dict


def _blob(entity: dict) -> str:
    return json.dumps(entity, ensure_ascii=False).lower()


def _match_patterns(text: str) -> dict | None:
    for pat in _mech_catalog().get("power_patterns") or []:
        if not isinstance(pat, dict):
            continue
        for m in pat.get("match") or []:
            if str(m).lower() in text:
                return pat
    return None


def _enemy_catalog_match(e: dict) -> dict | None:
    blob = _blob(e)
    for _key, ent in (_mech_catalog().get("enemies") or {}).items():
        if not isinstance(ent, dict):
            continue
        for n in ent.get("names") or []:
            if str(n).lower() in blob:
                return ent
    return None


def detect_enemy_mechanics(enemy: dict) -> tuple[int | None, str]:
    """Return (damage_cap_per_turn, coaching note)."""
    notes: list[str] = []
    cap: int | None = None

    ent = _enemy_catalog_match(enemy)
    if ent:
        try:
            cap = int(ent.get("damage_cap_per_turn"))
        except (TypeError, ValueError):
            cap = None
        if ent.get("combat_plan"):
            notes.append(str(ent["combat_plan"]))

    for p in enemy.get("powers") or []:
        if not isinstance(p, dict):
            continue
        text = _blob(p)
        hit = _match_patterns(text)
        if hit:
            try:
                c = int(hit.get("damage_cap_per_turn"))
                cap = c if cap is None else min(cap, c)
            except (TypeError, ValueError):
                pass
            if hit.get("note"):
                notes.append(str(hit["note"]))
        m = re.search(r"(\d+)\s*点?伤害", text)
        if m and ("上限" in text or "最多" in text or "cap" in text):
            cap = int(m.group(1))

    name = str(enemy.get("name") or "")
    if cap is None and ("珊瑚" in name or "coral" in name.lower()):
        cap = 15
        notes.append("鬼祟珊瑚类：默认每回合有效伤害≤15")

    note = "；".join(dict.fromkeys(notes)) if notes else ""
    return cap, note


def _build_enemy_sims(state: dict) -> list[EnemyMech]:
    out: list[EnemyMech] = []
    for e in (state.get("battle") or {}).get("enemies") or []:
        if not isinstance(e, dict):
            continue
        try:
            hp = int(e.get("hp", 0) or 0)
        except (TypeError, ValueError):
            hp = 0
        cap, note = detect_enemy_mechanics(e)
        vuln = enemy_vulnerable_stacks(e)
        out.append(
            EnemyMech(
                entity_id=str(e.get("entity_id") or e.get("id") or "?"),
                name=str(e.get("name") or e.get("id") or "?"),
                hp=hp,
                block=int(e.get("block", 0) or 0),
                vuln_stacks=vuln,
                damage_cap_per_turn=cap,
                notes=note,
            )
        )
    return out


def _is_aoe(card: dict) -> bool:
    cid = str(card.get("id", "")).upper()
    if cid in _AOE_IDS or any(x in cid for x in ("CLEAVE", "WHIRL", "BREAK")):
        return True
    tt = str(card.get("target_type") or "").lower()
    return "all" in tt


def _applies_vuln(card: dict) -> int:
    return card_applies_vulnerable(card)


def _play_cost(card: dict, energy: int) -> int:
    raw = str(card.get("cost", "99")).upper()
    if raw == "X":
        return max(0, energy)
    return _cost(card)


def _vuln_multiplier(stacks: int) -> float:
    return vulnerable_damage_multiplier(stacks)


def _whirlwind_damage(card: dict, x_spent: int, player: dict) -> int:
    desc = str(card.get("description", "") or "")
    per = 8
    m = re.search(r"(\d+)\s*.*次|(\d+)\s*damage", desc, re.I)
    if m:
        per = int(next(g for g in m.groups() if g))
    try:
        bonus = int(player.get("strength", 0) or 0)
    except (TypeError, ValueError):
        bonus = 0
    return max(0, (per + bonus) * max(1, x_spent))


def _effective_damage(
    card: dict, player: dict, enemy: EnemyMech, *, x_spent: int = 0
) -> int:
    cid = str(card.get("id", "")).upper()
    if cid == "WHIRLWIND" or "WHIRL" in cid:
        return _whirlwind_damage(card, x_spent, player)
    return estimate_card_damage(
        card,
        player,
        vuln_stacks=enemy.vuln_stacks,
        apply_vulnerable=True,
    )


def _apply_hit(enemy: EnemyMech, raw: int) -> int:
    """Apply damage after enemy block + per-turn cap; return effective HP loss."""
    if raw <= 0 or enemy.hp <= 0:
        return 0
    # raw already includes Vulnerable via estimate_card_damage (wiki: ×1.5 once)
    dmg = int(raw)
    if enemy.block > 0:
        absorbed = min(enemy.block, dmg)
        enemy.block -= absorbed
        dmg -= absorbed
    if dmg <= 0:
        return 0
    if enemy.damage_cap_per_turn is not None:
        cap = max(0, int(enemy.damage_cap_per_turn))
        room = max(0, cap - enemy.damage_taken_this_turn)
        dmg = min(dmg, room)
    enemy.hp = max(0, enemy.hp - dmg)
    enemy.damage_taken_this_turn += dmg
    return dmg


def _pick_target(enemies: list[EnemyMech]) -> EnemyMech | None:
    living = [e for e in enemies if e.hp > 0]
    if not living:
        return None
    return min(living, key=lambda e: e.hp)


def _simulate_play(ps: PlanState, card: dict) -> tuple[PlanState, dict, int]:
    """Return new state, action body, score delta for this play."""
    cost = _play_cost(card, ps.energy)
    if cost > ps.energy or not card.get("can_play", True):
        raise ValueError("illegal play")

    new = PlanState(
        energy=ps.energy - cost,
        player_block=ps.player_block,
        hand=[c for c in ps.hand if c.get("index") != card.get("index")],
        enemies=copy.deepcopy(ps.enemies),
        player=ps.player,
    )
    action: dict = {"action": "play_card", "card_index": card.get("index", 0)}
    score = 0.0

    if _card_is_block(card):
        gain = estimate_block_gain(card)
        new.player_block += gain
        score += gain * 2.0
        return new, action, int(score)

    if not (_card_is_attack(card) or _effective_damage(card, ps.player, _pick_target(new.enemies) or EnemyMech("?", "?", 1)) > 0):
        return new, action, 0

    x_spent = cost if str(card.get("cost", "")).upper() == "X" else 0
    raw = _effective_damage(card, ps.player, _pick_target(new.enemies) or EnemyMech("?", "?", 1), x_spent=x_spent)

    if _is_aoe(card):
        total = 0
        for e in new.enemies:
            if e.hp > 0:
                total += _apply_hit(e, raw)
        score += total * 3.0
    else:
        tgt = _pick_target(new.enemies)
        if tgt:
            action["target"] = tgt.entity_id
            eff = _apply_hit(tgt, raw)
            score += eff * 3.0
            vstacks = _applies_vuln(card)
            if vstacks:
                tgt.vuln_stacks = max(tgt.vuln_stacks, vstacks)
                score += 8.0

    return new, action, int(score)


def _score_terminal(ps: PlanState, incoming: int) -> float:
    score = 0.0
    try:
        hp = int(ps.player.get("hp", ps.player.get("current_hp", 1)))
    except (TypeError, ValueError):
        hp = 1
    net = max(0, incoming - ps.player_block)
    lethal = incoming > 0 and net >= hp

    for e in ps.enemies:
        score += max(0, 100 - e.hp) * 2.0
        if e.hp <= 0:
            score += 50.0
    if incoming > 0:
        gap = max(0, incoming - ps.player_block)
        score -= gap * 4.0
        score += min(ps.player_block, incoming) * 2.5
    if lethal:
        score -= 500.0
    if ps.energy > 0:
        score -= ps.energy * 12.0
    return score


def _search_best_sequence(
    ps: PlanState,
    *,
    incoming: int,
    depth: int = 0,
    max_depth: int = 8,
) -> tuple[float, list[dict]]:
    best_score = _score_terminal(ps, incoming)
    best_seq: list[dict] = []

    if depth >= max_depth or ps.energy <= 0:
        return best_score, best_seq

    playable = [
        c
        for c in ps.hand
        if c.get("can_play", True) and _play_cost(c, ps.energy) <= ps.energy
    ]
    playable.sort(
        key=lambda c: (
            0 if _card_is_attack(c) else 1 if _card_is_block(c) else 2,
            _cost(c),
        )
    )

    for card in playable[:10]:
        try:
            nxt, action, _ = _simulate_play(ps, card)
        except ValueError:
            continue
        sub_score, sub_seq = _search_best_sequence(
            nxt, incoming=incoming, depth=depth + 1, max_depth=max_depth
        )
        if sub_score > best_score:
            best_score = sub_score
            best_seq = [action] + sub_seq

    return best_score, best_seq


def plan_turn_sequence(state: dict) -> list[dict]:
    """Best-effort multi-card plan for current player turn."""
    player = state.get("player") or {}
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    hand = list(player.get("hand") or [])
    if energy <= 0 or not hand:
        return []

    ps = PlanState(
        energy=energy,
        player_block=int(player.get("block", 0) or 0),
        hand=hand,
        enemies=_build_enemy_sims(state),
        player=player,
    )
    incoming = incoming_attack_damage((state.get("battle") or {}).get("enemies") or [])
    _, seq = _search_best_sequence(ps, incoming=incoming)
    return seq


def battle_budget_block(state: dict) -> str:
    """HP / damage-cap rounds estimate at combat start or mid-fight."""
    enemies = _build_enemy_sims(state)
    living = [e for e in enemies if e.hp > 0]
    if not living:
        return ""
    lines = ["【战局预算·代码估算】"]
    for e in living:
        cap_txt = f"≤{e.damage_cap_per_turn}/回合" if e.damage_cap_per_turn else "无外壳上限"
        rounds = ""
        if e.damage_cap_per_turn and e.damage_cap_per_turn > 0:
            rounds = f" ≈{math.ceil(e.hp / e.damage_cap_per_turn)}回合打满有效伤"
        lines.append(f"  · {e.name} HP{e.hp} | {cap_txt}{rounds}")
        if e.notes:
            lines.append(f"    {e.notes}")
    p = state.get("player") or {}
    try:
        php = int(p.get("hp", 0))
    except (TypeError, ValueError):
        php = 0
    inc = incoming_attack_damage((state.get("battle") or {}).get("enemies") or [])
    lines.append(
        f"  我方HP{php} | 本回合预计入伤≈{inc} | "
        "规划时：先算组合伤害与外壳，再按序执行多次 sts2_act。"
    )
    return "\n".join(lines)


def format_line_plan_block(state: dict) -> str:
    """Inject into play_brief — turn plan + battle budget."""
    st = str(state.get("state_type") or "")
    if st not in ("monster", "elite", "boss"):
        return ""

    battle = state.get("battle") or {}
    turn = str(battle.get("turn") or "").lower()
    if turn and turn not in ("player", "play", "your_turn"):
        return ""

    parts: list[str] = [
        "【决策权】最终出牌由你（LLM）判断；下列计划/组合仅为辅助，可因抽牌/教练纠正而改。",
        battle_budget_block(state),
    ]
    combo = format_combo_alternatives(state)
    if combo:
        parts.append(combo)

    seq = plan_turn_sequence(state)
    if not seq:
        return "\n\n".join(p for p in parts if p)

    player = state.get("player") or {}
    lines = ["【本回合出牌计划·代码枚举】按序执行，每步后 get_state："]
    sim_enemies = _build_enemy_sims(state)
    ps = PlanState(
        energy=int(player.get("energy", 0) or 0),
        player_block=int(player.get("block", 0) or 0),
        hand=list(player.get("hand") or []),
        enemies=sim_enemies,
        player=player,
    )
    incoming = incoming_attack_damage((state.get("battle") or {}).get("enemies") or [])

    for i, action in enumerate(seq[:6], 1):
        idx = action.get("card_index")
        card = next((c for c in ps.hand if c.get("index") == idx), None)
        name = (card.get("name") if card else None) or f"index={idx}"
        note = ""
        if card:
            try:
                nxt, action_body, _ = _simulate_play(ps, card)
                tgt = action.get("target") or action_body.get("target", "")
                if _card_is_block(card):
                    note = f" → 格挡后≈{nxt.player_block}"
                else:
                    eff_hint = _effective_damage(
                        card, player, _pick_target(ps.enemies) or sim_enemies[0]
                    )
                    cap = ""
                    t0 = _pick_target(ps.enemies)
                    if t0 and t0.damage_cap_per_turn:
                        cap = f" (外壳后有效≤{t0.damage_cap_per_turn})"
                    note = f" → 约{eff_hint}伤{cap}" + (
                        f" 目标{tgt}" if tgt else " AOE"
                    )
                ps = nxt
            except ValueError:
                pass
        lines.append(f"  {i}. play_card card_index={idx} ({name}){note}")

    if ps.energy > 0:
        lines.append(
            f"  → 计划后仍余{ps.energy}能量：继续 get_state 补打或叠防，勿盲目 end_turn"
        )
    else:
        lines.append("  → 计划用尽能量后 end_turn")

    if incoming > ps.player_block:
        lines.append(
            f"  防向提示：预计入伤{incoming} > 现格挡{ps.player_block}，"
            "若计划偏输出请确认能扛或改连防序列。"
        )

    parts.append("\n".join(lines))
    return "\n\n".join(p for p in parts if p)


def first_planned_action(state: dict) -> dict | None:
    seq = plan_turn_sequence(state)
    return seq[0] if seq else None


def format_combo_alternatives(state: dict, *, limit: int = 3) -> str:
    """Top turn sequences for LLM — not auto-executed."""
    player = state.get("player") or {}
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    hand = list(player.get("hand") or [])
    if energy <= 0 or not hand:
        return ""

    ps0 = PlanState(
        energy=energy,
        player_block=int(player.get("block", 0) or 0),
        hand=hand,
        enemies=_build_enemy_sims(state),
        player=player,
    )
    incoming = incoming_attack_damage((state.get("battle") or {}).get("enemies") or [])

    scored: list[tuple[float, list[dict], PlanState]] = []

    def _collect(ps: PlanState, seq: list[dict], depth: int) -> None:
        sc = _score_terminal(ps, incoming)
        scored.append((sc, list(seq), ps))
        if depth >= 6 or ps.energy <= 0:
            return
        playable = [
            c
            for c in ps.hand
            if c.get("can_play", True) and _play_cost(c, ps.energy) <= ps.energy
        ]
        for card in playable[:8]:
            try:
                nxt, act, _ = _simulate_play(ps, card)
            except ValueError:
                continue
            _collect(nxt, seq + [act], depth + 1)

    _collect(ps0, [], 0)
    if not scored:
        return ""
    scored.sort(key=lambda x: x[0], reverse=True)
    seen: set = set()
    lines = ["【组合伤害·枚举参考】（由你判断是否采纳，非自动出牌）"]
    shown = 0
    for sc, seq, end_ps in scored:
        if not seq:
            continue
        key = tuple(a.get("card_index") for a in seq)
        if key in seen:
            continue
        seen.add(key)
        shown += 1
        if shown > limit:
            break
        names = []
        for a in seq:
            idx = a.get("card_index")
            c = next((x for x in hand if x.get("index") == idx), {})
            names.append(str(c.get("name") or idx))
        eff = sum(e.damage_taken_this_turn for e in end_ps.enemies)
        lines.append(
            f"  方案{shown}: {' → '.join(names)} | 模拟有效伤≈{eff} "
            f"格挡{end_ps.player_block} 余能{end_ps.energy} 分{sc:.0f}"
        )
    return "\n".join(lines) if len(lines) > 1 else ""


def check_action_vs_plan(
    before: dict,
    after: dict,
    body: dict,
) -> list[str]:
    """Warnings when LLM action diverges from energy/shell discipline."""
    warnings: list[str] = []
    action = str(body.get("action") or "")
    if str(before.get("state_type") or "") not in ("monster", "elite", "boss"):
        return warnings

    try:
        energy_before = int((before.get("player") or {}).get("energy", 0))
    except (TypeError, ValueError):
        energy_before = 0

    if action == "end_turn" and energy_before > 0:
        hand = (before.get("player") or {}).get("hand") or []
        from plugins.sts2.combat_brain import _affordable

        if _affordable(hand, energy_before):
            seq = plan_turn_sequence(before)
            if seq:
                warnings.append(
                    f"仍有{energy_before}能量且可出牌，计划建议继续: "
                    + " → ".join(
                        f"index={a.get('card_index')}" for a in seq[:3]
                    )
                )
            else:
                warnings.append(f"仍有{energy_before}能量未用就 end_turn")

    if action == "play_card":
        caps = [
            e.damage_cap_per_turn
            for e in _build_enemy_sims(before)
            if e.damage_cap_per_turn and e.hp > 0
        ]
        if caps:
            cap = min(caps)
            loss = 0
            before_es = {
                str(e.get("entity_id") or e.get("id")): int(e.get("hp", 0) or 0)
                for e in (before.get("battle") or {}).get("enemies") or []
                if isinstance(e, dict)
            }
            for e in (after.get("battle") or {}).get("enemies") or []:
                if not isinstance(e, dict):
                    continue
                key = str(e.get("entity_id") or e.get("id"))
                loss += max(0, before_es.get(key, 0) - int(e.get("hp", 0) or 0))
            if loss < cap * 0.55 and energy_before >= 2:
                warnings.append(
                    f"外壳战本步后本回合累计有效伤≈{loss}，上限{cap}/回合，宜打满再 end"
                )

    return warnings
