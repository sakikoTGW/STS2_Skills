"""Rich combat coaching block for play_brief (multi-turn, lethal math, legal actions)."""

from __future__ import annotations

import json
from typing import Any

from plugins.sts2.combat_brain import (
    _affordable,
    _card_is_attack,
    _card_is_block,
    _card_is_power,
    _cost,
    _target_entity_id,
    block_play_is_urgent,
    combat_should_end_turn,
    combat_should_wait,
    estimate_block_gain,
    estimate_card_damage,
    incoming_attack_damage,
    is_safe_from_incoming,
    net_incoming_damage,
    try_lethal_attack,
)
from plugins.sts2.combat_play_brain import (
    _enemy_wiki_brief,
    _hand_cards,
    _hand_wiki_block,
    _prefetch_hand_wiki,
)

_COMBAT = frozenset({"monster", "elite", "boss", "hand_select"})


def format_combat_brief(state: dict) -> str:
    """Full combat coaching — used by play_brief._combat_block."""
    if not state:
        return ""
    st = str(state.get("state_type") or "")
    if st not in _COMBAT:
        return ""

    battle = state.get("battle") or {}
    turn = str(battle.get("turn") or "").lower()
    if turn and turn not in ("player", "play", "your_turn"):
        return "【敌方回合】本回合只能等待（不要 play_card / end_turn）。"

    # MCP 有时缺 is_play_phase；turn=player 时仍输出完整 brief
    if battle.get("is_play_phase") is False and turn in ("player", "play", "your_turn"):
        return "【非出牌阶段】等待动画；勿 play_card / end_turn。"
    if combat_should_wait(state) and st != "hand_select" and turn not in (
        "player",
        "play",
        "your_turn",
    ):
        return "【敌方回合/非出牌阶段】等待动画；勿 play_card / end_turn。"

    from plugins.sts2.config import load_sts2_config

    cfg = load_sts2_config()
    hand = _hand_cards(state)
    _prefetch_hand_wiki(hand, int(cfg.get("study_combat_wiki_max_fetches", 4)))

    try:
        from plugins.sts2.run_objective import format_run_objective_block

        run_block = format_run_objective_block(state)
    except Exception:
        run_block = ""

    try:
        from plugins.sts2.build_knowledge import format_build_combat_hint, format_layer_threat_block

        build_hint = format_build_combat_hint(state)
        layer_threat = format_layer_threat_block(state)
    except Exception:
        build_hint = ""
        layer_threat = ""

    survival = ""
    try:
        from plugins.sts2.combat_survival_gate import format_survival_gate_block

        survival = format_survival_gate_block(state)
    except Exception:
        survival = ""

    sections: list[str] = [
        survival,
        run_block,
        build_hint,
        layer_threat,
        _battle_header(state),
        _player_panel(state),
        _enemy_panel(state),
        _damage_ledger(state),
        _enemy_wiki_brief(state),
        _hand_wiki_block(hand),
        _hand_tactics(state, hand),
        _lethal_panel(state, hand),
        _damage_control_panel(state, hand),
        _potion_panel(state),
        _energy_spend_plan(state, hand),
        _line_plan_block(state),
        _turn_decision(state, hand),
        _intent_notes(state),
    ]

    try:
        from plugins.sts2.combat_turn_plan import format_turn_plan_block

        plan = format_turn_plan_block(state)
        if plan:
            sections.append(plan)
    except Exception:
        pass

    sections.append(_legal_actions_sheet(state, hand))
    if st == "hand_select":
        sections.append(_hand_select_note(state))

    return "\n\n".join(s for s in sections if s)


def _battle_header(state: dict) -> str:
    st = str(state.get("state_type") or "?")
    run = state.get("run") or {}
    battle = state.get("battle") or {}
    floor = run.get("floor", "?")
    act = run.get("act", "?")
    ch = run.get("character") or run.get("character_id") or "?"
    rnd = battle.get("round", "?")
    turn = battle.get("turn", "?")
    phase = "出牌" if battle.get("is_play_phase", True) else "非出牌"
    enc = {"monster": "普通战", "elite": "精英", "boss": "Boss", "hand_select": "战斗·选牌"}.get(
        st, st
    )
    return (
        f"【战场】{enc} | {ch} | 幕{act} 第{floor}层 | 回合{rnd} ({turn}/{phase})"
    )


def _fmt_powers(powers: Any, limit: int = 8) -> str:
    if not powers:
        return "(无)"
    bits: list[str] = []
    for p in powers:
        if not isinstance(p, dict):
            continue
        name = p.get("name") or p.get("id") or "?"
        amt = p.get("amount", p.get("stacks", p.get("count")))
        if amt is not None:
            bits.append(f"{name}×{amt}")
        else:
            bits.append(str(name))
        if len(bits) >= limit:
            break
    return ", ".join(bits) if bits else "(无)"


def _player_panel(state: dict) -> str:
    p = state.get("player") or {}
    try:
        hp = int(p.get("hp", p.get("current_hp", 0)))
        mx = int(p.get("max_hp", hp) or hp or 1)
        blk = int(p.get("block", 0))
        en = int(p.get("energy", 0))
    except (TypeError, ValueError):
        hp, mx, blk, en = 0, 1, 0, 0
    pct = int(100 * hp / mx) if mx else 0
    strn = p.get("strength", p.get("str"))
    dex = p.get("dexterity", p.get("dex"))
    stat_bits = []
    if strn not in (None, 0, "0"):
        stat_bits.append(f"力{strn}")
    if dex not in (None, 0, "0"):
        stat_bits.append(f"敏{dex}")
    stats = " | ".join(stat_bits) if stat_bits else ""
    lines = [
        f"【我方】HP {hp}/{mx} ({pct}%) | 格挡{blk} | 能量{en}"
        + (f" | {stats}" if stats else ""),
        f"  能力: {_fmt_powers(p.get('powers'))}",
    ]
    relics = p.get("relics") or []
    if relics:
        rnames = [
            str(r.get("name") or r.get("id") or "?")
            for r in relics[:6]
            if isinstance(r, dict)
        ]
        if rnames:
            lines.append("  遗物: " + ", ".join(rnames))
    return "\n".join(lines)


def _enemy_intent_line(e: dict) -> str:
    intents = e.get("intents") or []
    if not intents or not isinstance(intents[0], dict):
        return "意图:?"
    it = intents[0]
    from plugins.sts2.combat_brain import _parse_intent_damage

    dmg = _parse_intent_damage(it)
    typ = it.get("type") or "?"
    label = it.get("label") or it.get("description") or ""
    hits = it.get("hits") or it.get("count")
    hit_txt = f" ×{hits}击" if hits and int(hits) > 1 else ""
    blk_e = e.get("block")
    blk_txt = f" | 敌格挡{blk_e}" if blk_e not in (None, 0, "0") else ""
    facing = e.get("facing") or e.get("orientation") or e.get("side")
    face_txt = f" | 朝向:{facing}" if facing else ""
    return f"意图 {typ}/{label} 伤害≈{dmg}{hit_txt}{blk_txt}{face_txt}"


def _enemy_panel(state: dict) -> str:
    enemies = [
        e for e in (state.get("battle") or {}).get("enemies") or [] if isinstance(e, dict)
    ]
    if not enemies:
        return "【敌人】无"
    lines = ["【敌人战况】"]
    for i, e in enumerate(enemies):
        name = e.get("name") or e.get("id") or f"敌人{i}"
        eid = e.get("entity_id") or e.get("id") or "?"
        try:
            hp = int(e.get("hp", 0))
            mx = int(e.get("max_hp", hp) or hp or 1)
        except (TypeError, ValueError):
            hp, mx = 0, 1
        hp_pct = int(100 * hp / mx) if mx else 0
        lines.append(
            f"  [{i}] {name}  HP{hp}/{mx}({hp_pct}%)  id={eid}"
        )
        lines.append(f"      {_enemy_intent_line(e)}")
        pows = _fmt_powers(e.get("powers"), limit=5)
        if pows != "(无)":
            lines.append(f"      能力: {pows}")
    return "\n".join(lines)


def _behavior_loop_ledger(enemies: list[dict]) -> list[str]:
    """Per-enemy KB loop forecast — shown in play_brief damage ledger."""
    out: list[str] = []
    try:
        from plugins.sts2.huiji_kb.loops import forecast_enemy, format_loop_forecast
        from plugins.sts2.huiji_kb.store import lookup_enemy
        from plugins.sts2.wiki_enemy import normalize_enemy_wiki_id
    except Exception:
        return out

    for e in enemies:
        if not isinstance(e, dict) or int(e.get("hp", 0) or 0) <= 0:
            continue
        name = e.get("name") or e.get("id") or "?"
        wid = normalize_enemy_wiki_id(e)
        kb = lookup_enemy(wid) if wid else None
        if not kb or not (kb.get("behavior_loop") or {}).get("steps"):
            out.append(
                f"  · {name} key={wid or '?'}: ⚠ 无本地行为循环 — "
                "勿臆测 T+1；hermes sts2 sync-wiki 或补 enemies.json"
            )
            continue
        fc = forecast_enemy(kb, e, horizon=3)
        bit = format_loop_forecast(fc)
        if bit:
            out.append(f"  · {name}: {bit}")
    return out


def _per_enemy_incoming(e: dict) -> int:
    from plugins.sts2.combat_brain import _parse_intent_damage

    total = 0
    for intent in e.get("intents") or []:
        if not isinstance(intent, dict):
            continue
        itype = str(intent.get("type", "")).lower()
        if itype in ("buff", "debuff", "sleep", "stun", "defend", "block", "heal", "card"):
            continue
        dmg = _parse_intent_damage(intent)
        hits = intent.get("hits") or intent.get("count") or 1
        try:
            hits_i = max(1, int(hits))
        except (TypeError, ValueError):
            hits_i = 1
        if dmg > 0:
            total += dmg * hits_i
        elif str(intent.get("label", "")).strip().isdigit():
            total += int(intent.get("label"))
    return total


def _damage_ledger(state: dict) -> str:
    p = state.get("player") or {}
    enemies = (state.get("battle") or {}).get("enemies") or []
    try:
        blk = int(p.get("block", 0))
        hp = int(p.get("hp", p.get("current_hp", 0)))
    except (TypeError, ValueError):
        blk, hp = 0, 0

    inc_total = incoming_attack_damage(enemies)
    net = net_incoming_damage(inc_total, blk)
    safe = is_safe_from_incoming(inc_total, blk, hp)

    lines = ["【伤害账本】"]
    loop_lines = _behavior_loop_ledger(enemies)
    for e in enemies:
        if not isinstance(e, dict):
            continue
        name = e.get("name") or e.get("id") or "?"
        inc_e = _per_enemy_incoming(e)
        if inc_e > 0:
            lines.append(f"  · {name}: 本回合攻击≈{inc_e}")
        else:
            lines.append(f"  · {name}: 本回合无攻击意图（Buff/防/休息等）")
    if loop_lines:
        lines.append("【行为循环·可计算】（禁止写「推测攻击」，用下行 T+1/T+2）")
        lines.extend(loop_lines)

    lines.append(
        f"  合计下回合入伤≈{inc_total} | 我方格挡{blk} | 净入伤{net} | HP{hp}"
    )
    if inc_total == 0:
        lines.append("  → 非攻击回合：优先输出/上 debuff，少堆无用格挡")
    elif safe and inc_total > 0:
        lines.append(
            "  → 本回合打不死你：若多回合计划里本回合是输出窗，可输出/斩杀；"
            "否则留费给下回合高伤（局内最优>单回合贪心）"
        )
    elif net >= hp and hp > 0:
        lines.append("  → 挡不住会死：必须先防/药水/转向减伤")
    elif block_play_is_urgent(state):
        lines.append("  → 建议本回合打出格挡（净伤≥HP）")
    elif net > 0:
        lines.append(f"  → 会吃{net}伤但不致死；权衡格挡 vs 输出")
    return "\n".join(lines)


def _card_target_hint(
    card: dict, enemies: list[dict], player: dict, *, state: dict | None = None
) -> str:
    tt = str(card.get("target_type") or card.get("target") or "").lower()
    if tt in ("self", "none", "") and "enemy" not in tt:
        if _card_is_block(card) or _card_is_power(card):
            return "无需 target"
        if not _card_is_attack(card):
            return "按牌面"
    living = [e for e in enemies if int(e.get("hp", 0) or 0) > 0]
    if not living:
        return "无目标"
    if len(living) == 1:
        e = living[0]
        return f"target={e.get('entity_id')} ({e.get('name')})"
    low = min(living, key=lambda e: int(e.get("hp", 9999)))
    eid = low.get("entity_id")
    from plugins.sts2.combat_turn_plan import _enemy_key, predict_next_turn

    key = _enemy_key(low)
    pred, note = predict_next_turn(key)
    if pred == "likely_non_attack":
        return f"慎选 {eid}（下回合常休息）| 优先打将攻击的怪"
    dmg = estimate_card_damage(card, player, state=state or {}, enemy=low)
    if dmg >= int(low.get("hp", 0) or 0):
        return f"斩杀 target={eid} ({low.get('name')})"
    return f"默认 target={eid}（血最少）"


def _hand_tactics(state: dict, hand: list[dict]) -> str:
    if not hand:
        return "【手牌战术】手牌为空（可能在补牌动画）"
    player = state.get("player") or {}
    enemies = (state.get("battle") or {}).get("enemies") or []
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    playable = _affordable(hand, energy)

    lines = [
        f"【手牌战术】能量{energy} | 可打出{len(playable)}/{len(hand)}张",
        "  play_card 用 card_index；有目标牌必须带 target=entity_id",
        "  出牌后 index 左移（右侧牌 index 减 1）",
    ]
    for c in hand:
        idx = c.get("index", "?")
        cost = c.get("cost", "?")
        name = c.get("name") or c.get("id") or "?"
        ok = c.get("can_play", False) and _cost(c) <= energy
        tag = "✓可出" if ok else "×不可"
        if not c.get("can_play") and _cost(c) <= energy:
            reason = c.get("unplayable_reason") or "条件不满足"
            tag = f"×({reason})"
        elif _cost(c) > energy:
            tag = f"×(费{cost}>能{energy})"

        extras: list[str] = []
        if _card_is_block(c):
            extras.append(f"格挡≈{estimate_block_gain(c, player)}")
        if _card_is_attack(c):
            from plugins.sts2.combat_brain import format_attack_damage_hint

            hint_dmg = format_attack_damage_hint(c, player, state)
            extras.append(hint_dmg or f"伤害≈{estimate_card_damage(c, player, state=state)}")
        if _card_is_power(c):
            extras.append("能力牌")
        hint = _card_target_hint(c, enemies, player, state=state) if ok else ""
        extra_s = " | ".join(extras)
        line = f"  [{idx}] {name} 费{cost} {tag}"
        if extra_s:
            line += f" | {extra_s}"
        if hint:
            line += f" → {hint}"
        lines.append(line)
    return "\n".join(lines)


def _lethal_panel(state: dict, hand: list[dict]) -> str:
    player = state.get("player") or {}
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    playable = _affordable(hand, energy)
    attacks = [c for c in playable if _card_is_attack(c)]
    enemies = [
        e for e in (state.get("battle") or {}).get("enemies") or [] if isinstance(e, dict)
    ]
    living = [e for e in enemies if int(e.get("hp", 0) or 0) > 0]
    if not living or not attacks:
        return ""

    from plugins.sts2.combat_brain import player_attack_damage_multiplier

    atk_mult = player_attack_damage_multiplier(state)
    mult_note = ""
    if atk_mult < 0.999:
        mult_note = f"（含 Shrink/Frail 等，攻击×{atk_mult:.2f}）"

    lines = ["【斩杀线】"]
    for e in living:
        name = e.get("name") or "?"
        eid = e.get("entity_id")
        need = int(e.get("hp", 0) or 0)
        killers = [
            c
            for c in attacks
            if estimate_card_damage(c, player, state=state) >= need
        ]
        if killers:
            best = min(killers, key=lambda c: (_cost(c), c.get("index", 0)))
            lines.append(
                f"  · {name} HP{need} → 可斩杀: [{best.get('index')}]"
                f" {best.get('name')} target={eid}"
            )
        else:
            total = sum(estimate_card_damage(c, player, state=state) for c in attacks)
            lines.append(
                f"  · {name} HP{need} → 本回合杀不死(剩攻合计≈{total}{mult_note})"
            )

    lethal_body = try_lethal_attack(state)
    if lethal_body:
        lines.append(
            f"  ★ 规则引擎建议: play_card index={lethal_body.get('card_index')}"
            f" target={lethal_body.get('target', '')}"
        )
    return "\n".join(lines)


def _damage_control_panel(state: dict, hand: list[dict]) -> str:
    """When kill is impossible this turn but enemy attacks next — prefer block over chip."""
    player = state.get("player") or {}
    try:
        energy = int(player.get("energy", 0))
        blk = int(player.get("block", 0))
    except (TypeError, ValueError):
        energy, blk = 0, 0
    if energy <= 0:
        return ""

    playable = _affordable(hand, energy)
    attacks = [c for c in playable if _card_is_attack(c)]
    blocks = [c for c in playable if _card_is_block(c)]
    if not attacks or not blocks:
        return ""

    living = [
        e
        for e in (state.get("battle") or {}).get("enemies") or []
        if isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0
    ]
    if not living:
        return ""

    focus = min(living, key=lambda e: int(e.get("hp", 9999)))
    need = int(focus.get("hp", 0) or 0)
    max_chip = max(estimate_card_damage(c, player, state=state) for c in attacks)
    total_chip = sum(estimate_card_damage(c, player, state=state) for c in attacks)
    if max_chip >= need:
        return ""

    from plugins.sts2.combat_brain import (
        next_turn_incoming_from_loops,
        player_attack_damage_multiplier,
    )

    inc_loop = next_turn_incoming_from_loops(state)
    inc_intent = incoming_attack_damage(living)
    inc_next = inc_loop if inc_loop > 0 else inc_intent
    if inc_next <= 0:
        return ""

    best_blk = max(blocks, key=lambda c: estimate_block_gain(c, player))
    gain = estimate_block_gain(best_blk, player)
    projected = blk + gain
    name = focus.get("name") or "?"

    lines = [
        "【战损纪律·勿蹭伤】",
        f"  · {name} HP{need}：本回合剩攻最多≈{max_chip}（合计≈{total_chip}），杀不死。",
    ]
    mult = player_attack_damage_multiplier(state)
    if mult < 0.999:
        lines.append(
            f"  · 你带 Shrink 等：攻击约×{mult:.2f}，蹭 1 费打击常只有 2～3 伤，仍要下回合补牌收怪。"
        )
    lines.append(
        f"  · 敌方下动（行为循环 T+1）≈{inc_next} 伤；剩 {energy} 费优先叠防"
        f"（如 [{best_blk.get('index')}] {best_blk.get('name')} +{gain}，叠后格挡≈{projected}），"
        "再 end_turn。"
    )
    lines.append(
        "  · 下回合必抽新牌，凌虐/打击/上勾拳足以收掉残血；"
        "不要为了 2～3 蹭伤白吃一刀 — 通关>单回合贪心。"
    )
    if projected >= inc_next:
        lines.append(f"  → 叠防后可挡满 T+1≈{inc_next}，战损≈0。")
    elif projected > blk:
        lines.append(
            f"  → 叠防后仍吃≈{max(0, inc_next - projected)} 伤，仍优于裸脸吃 {inc_next}。"
        )
    return "\n".join(lines)


def _potion_panel(state: dict) -> str:
    pots = (state.get("player") or {}).get("potions") or []
    if not pots:
        return ""
    lines = ["【药水】use_potion slot=0|1|2（战斗内）"]
    for slot, pot in enumerate(pots):
        if not pot:
            lines.append(f"  slot{slot}: (空)")
            continue
        name = pot.get("name") or pot.get("id") or "?"
        usable = pot.get("can_use_in_combat", True)
        mark = "可用" if usable is not False else "不可用"
        desc = str(pot.get("description") or "")[:60]
        lines.append(f"  slot{slot}: {name} [{mark}] {desc}")

    try:
        from plugins.sts2.combat_resources import prefer_potion_play

        sug = prefer_potion_play(state)
        if sug:
            lines.append(
                f"  → 资源规则建议: {json.dumps(sug, ensure_ascii=False)}"
            )
    except Exception:
        pass
    return "\n".join(lines)


def _line_plan_block(state: dict) -> str:
    try:
        from plugins.sts2.combat_line_planner import format_line_plan_block

        return format_line_plan_block(state)
    except Exception as exc:
        return f"【出牌计划】规划器暂不可用: {exc}"


def _energy_spend_plan(state: dict, hand: list[dict]) -> str:
    """Explicit: spend all energy in one player turn across multiple sts2_act calls."""
    player = state.get("player") or {}
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    try:
        blk = int(player.get("block", 0))
    except (TypeError, ValueError):
        blk = 0
    playable = _affordable(hand, energy)
    if energy <= 0 and combat_should_end_turn(state):
        return (
            "【能量纪律】能量已尽 → end_turn。"
            "（每次 sts2_act 仍只发一个 JSON；整回合可多次 act。）"
        )
    if energy <= 0 or not playable:
        return ""

    inc = incoming_attack_damage((state.get("battle") or {}).get("enemies") or [])
    lines = [
        "【能量纪律】本玩家回合内尽量用尽能量再 end_turn。",
        f"  当前能量{energy}，可出牌{len(playable)}张。",
        "  工具：sts2_act 打一张 → get_state(_fresh_state) → 可继续打，勿整回合只出一张。",
    ]

    blocks = sorted(
        [c for c in playable if _card_is_block(c)],
        key=lambda c: -estimate_block_gain(c, player),
    )
    if inc > blk and blocks:
        rem = energy
        projected = blk
        n_plays = 0
        for c in blocks:
            cost = _cost(c)
            if cost > rem:
                continue
            projected += estimate_block_gain(c, player)
            rem -= cost
            n_plays += 1
            if projected >= inc:
                break
        if n_plays >= 2:
            lines.append(
                f"  → 下回合入伤≈{inc}、现格挡{blk}：建议连打{n_plays}张防至≥{inc}，"
                "不要只叠一张就 end_turn。"
            )
        elif n_plays == 1 and inc > projected:
            lines.append(
                f"  → 入伤≈{inc}：至少再打1张防（现格挡{blk}），有费继续叠。"
            )
    elif inc == 0 and energy >= 2:
        lines.append("  → 敌人非攻击意图：可输出/上 debuff，勿为留能而只打一张防。")

    lethal = try_lethal_attack(state)
    if lethal and energy > 0:
        lines.append("  → 可斩杀：优先按 lethal 计划打满伤害再 end_turn。")

    return "\n".join(lines)


def _turn_decision(state: dict, hand: list[dict]) -> str:
    lines: list[str] = []
    if combat_should_end_turn(state):
        lines.append(
            "【回合动作】手牌/能量已用尽 → sts2_act {\"action\":\"end_turn\"}"
            "（勿 proceed；__wait__ 不会结束回合）"
        )
    elif not hand:
        try:
            en = int((state.get("player") or {}).get("energy", 0))
        except (TypeError, ValueError):
            en = 0
        if en > 0:
            lines.append("【回合动作】等待发牌动画后再 get_state")
    else:
        player = state.get("player") or {}
        try:
            energy = int(player.get("energy", 0))
        except (TypeError, ValueError):
            energy = 0
        playable = _affordable(hand, energy)
        if playable and not combat_should_end_turn(state):
            c0 = playable[0]
            tgt = _target_entity_id((state.get("battle") or {}).get("enemies") or [])
            ex = {"action": "play_card", "card_index": c0.get("index", 0)}
            if tgt and _card_is_attack(c0):
                ex["target"] = tgt
            lines.append(
                "【回合动作】仍有能量 → 继续出牌（下一动示例，打完再 get_state）: "
                + json.dumps(ex, ensure_ascii=False)
            )
    return "\n".join(lines)


def _intent_notes(state: dict) -> str:
    """Per-enemy intent coaching (buff turn vs attack turn)."""
    enemies = (state.get("battle") or {}).get("enemies") or []
    bits: list[str] = []
    for e in enemies:
        if not isinstance(e, dict):
            continue
        name = e.get("name") or e.get("id") or "?"
        intents = e.get("intents") or []
        if not intents or not isinstance(intents[0], dict):
            continue
        it = intents[0]
        typ = str(it.get("type") or "").lower()
        label = str(it.get("label") or it.get("description") or "")
        low = label.lower()
        if typ in ("buff", "debuff", "sleep", "stun") or any(
            k in low for k in ("buff", "debuff", "sleep", "stun", "强化", "虚弱", "休息")
        ):
            bits.append(f"{name}: 非主攻回合 → 输出/易伤/虚弱优先，少堆格挡")
        elif typ in ("attack", "multi_attack") or "damage" in low or "攻击" in label:
            bits.append(f"{name}: 攻击回合 → 先算净伤再决定是否格挡")
    if not bits:
        return ""
    return "【意图速读】\n" + "\n".join(f"  · {b}" for b in bits)


def _legal_actions_sheet(state: dict, hand: list[dict]) -> str:
    """Concrete JSON the model can copy."""
    player = state.get("player") or {}
    try:
        energy = int(player.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    playable = _affordable(hand, energy)
    enemies = (state.get("battle") or {}).get("enemies") or []
    tgt = _target_entity_id(enemies)

    opts: list[str] = []
    for c in playable[:5]:
        body: dict[str, Any] = {"action": "play_card", "card_index": c.get("index", 0)}
        tt = str(c.get("target_type") or "").lower()
        if tgt and ("enemy" in tt or _card_is_attack(c)):
            body["target"] = tgt
        name = c.get("name") or c.get("id")
        opts.append(f"  {name}: {json.dumps(body, ensure_ascii=False)}")

    if combat_should_end_turn(state):
        opts.append('  end_turn: {"action":"end_turn"}')
    lines = ["【合法动作速查】"]
    if opts:
        lines.extend(opts)
    else:
        lines.append("  (当前无费可出的牌)")
    lines.append('  等待: {"action":"__wait__"}')
    return "\n".join(lines)


def _hand_select_note(state: dict) -> str:
    hs = state.get("hand_select") or {}
    prompt = hs.get("prompt") or hs.get("mode") or "选牌"
    lines = [
        f"【战斗选牌】{prompt}",
        "  combat_select_card index=N 切换选中；combat_confirm_selection 确认",
        "  勿用 menu_select / choose_event_option / select_card_reward",
    ]
    if hs.get("can_confirm"):
        lines.append("  → 已可 confirm")
    return "\n".join(lines)
