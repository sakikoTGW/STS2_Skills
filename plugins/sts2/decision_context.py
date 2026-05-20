"""Unified decision context for agent-play — one assembly order for every screen.

Architecture (read top → bottom each get_state):
  L0  macro     — run goal, deck archetype, act threats
  L1  compute   — combat: survival math + behavior loops (computable)
  L2  screen    — map / reward / event / rest / combat detail
  L3  discipline — tool loop, index rules
  L4  memory    — cross-run strategy + lessons

Only the main Hermes agent decides; this module only *formats facts*.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_COMBAT = frozenset({"monster", "elite", "boss", "hand_select"})


def layer_macro(state: dict) -> str:
    """L0 — whole-run strategy (every screen)."""
    st = str(state.get("state_type") or "")
    parts: List[str] = []
    if st in ("card_reward", "card_select"):
        try:
            from plugins.sts2.card_pick_brain import summarize_deck, _archetype_hint
            from plugins.sts2.reward_cards import format_card_offers, offer_reward_cards

            offers = offer_reward_cards(state)
            parts.append("【L0·选牌构筑·必读】")
            parts.append(summarize_deck(state))
            hint = _archetype_hint(state)
            if hint:
                parts.append(hint)
            parts.append(format_card_offers(state, offers))
        except Exception:
            pass
    try:
        from plugins.sts2.run_act_planner import format_global_play_header

        hdr = format_global_play_header(state)
        if hdr:
            parts.append(hdr)
    except Exception:
        pass
    try:
        from plugins.sts2.knowledge_pack import macro_strategy_block

        macro = macro_strategy_block(state)
        if macro:
            parts.append(macro)
    except Exception:
        pass
    try:
        from plugins.sts2.lessons import lessons_for_screen

        les = lessons_for_screen(state)
        if les:
            parts.append("【跨局教训】\n" + "\n".join(f"- {x}" for x in les))
    except Exception:
        pass
    return "\n\n".join(p for p in parts if p)


def layer_game_flow(state: dict) -> str:
    """L0.5 — ascension, ancients heal, rest, map flow, full-hand plan."""
    parts: List[str] = []
    try:
        from plugins.sts2.game_flow_kb.brief import format_game_flow_brief

        block = format_game_flow_brief(state)
        if block:
            parts.append(block)
    except Exception:
        pass
    try:
        from plugins.sts2.wiki_crawl.lookup import format_wiki_facts_block

        wiki = format_wiki_facts_block(state)
        if wiki:
            parts.append(wiki)
    except Exception:
        pass
    return "\n\n".join(parts)


def layer_compute(state: dict) -> str:
    """L1 — numbers the agent must use before acting (combat-first)."""
    st = str(state.get("state_type") or "")
    if st not in _COMBAT:
        return ""

    parts: List[str] = ["【算数层·先读再动】"]
    checklist = thinking_checklist(state)
    if checklist:
        parts.append(checklist)

    snap = state.get("survival_snapshot")
    if not isinstance(snap, dict) or not snap.get("active", True):
        try:
            from plugins.sts2.combat_survival_gate import survival_snapshot

            snap = survival_snapshot(state)
        except Exception:
            snap = {}
    if isinstance(snap, dict) and snap.get("active", True):
        try:
            inc = int(snap.get("incoming_damage") or 0)
            blk = int(snap.get("player_block") or 0)
            net = int(snap.get("net_damage") or 0)
            hp = int(snap.get("hp") or 0)
            parts.append(
                f"  净入伤={net} (意图合计{inc} − 格挡{blk}) | HP={hp} | "
                f"可叠防≈{snap.get('block_gain_available', '?')}"
            )
            if snap.get("must_block"):
                parts.append("  ⚠ 必须格挡/药水后再输出")
            if snap.get("can_lethal"):
                parts.append("  ✓ 存在斩杀线 — 优先收尾")
        except (TypeError, ValueError):
            pass

    try:
        from plugins.sts2.combat_brain import format_hand_damage_ledger

        ledger = format_hand_damage_ledger(state)
        if ledger:
            parts.append(ledger)
    except Exception:
        pass

    return "\n\n".join(p for p in parts if p)


def layer_screen(state: dict) -> str:
    """L2 — screen-specific coaching (delegates to play_brief formatters)."""
    from plugins.sts2.play_brief import build_screen_brief

    return build_screen_brief(state)


def layer_discipline(state: dict) -> str:
    """L3 — tool / index discipline."""
    from plugins.sts2.play_brief import discipline_block

    return discipline_block(state)


def layer_memory(state: dict) -> str:
    """L4 — notes / manual learn context."""
    parts: List[str] = []
    try:
        from plugins.sts2.notes import recall_block

        recall = recall_block()
        if recall:
            parts.append(recall[:2000])
    except Exception:
        pass
    try:
        from plugins.sts2.manual_learn import build_learn_context

        learn = build_learn_context()
        if learn:
            parts.append(learn)
    except Exception:
        pass
    return "\n\n".join(p for p in parts if p)


def assemble_play_brief(state: dict) -> str:
    """Single entry: ordered decision context for sts2_get_state → play_brief."""
    if not state:
        return "(无状态)"
    layers = (
        layer_macro,
        layer_game_flow,
        layer_compute,
        layer_screen,
        layer_discipline,
        layer_memory,
    )
    parts: List[str] = []
    for fn in layers:
        block = fn(state)
        if block:
            parts.append(block)
    return "\n\n".join(parts)


def thinking_checklist(state: dict) -> str:
    """Fixed reply skeleton for combat turns (agent writes in chat)."""
    st = str(state.get("state_type") or "")
    if st not in _COMBAT:
        return ""

    lines = [
        "【思考模板·战斗回合请在回复中写清】",
        "1) T+0: 意图合计→净入伤(见算数层) | 能否本回合击杀",
        "2) 行为循环: 读【怪物Wiki】行为循环行 → T+1/T+2 估伤",
        "3) 本动: 打/防/药 —— 构筑主轴 + 循环位置理由",
        "4) 杀线/防線: 需格挡≥X 或 再打Y伤收怪",
    ]

    enemies = (state.get("battle") or {}).get("enemies") or []
    loop_bits: List[str] = []
    try:
        from plugins.sts2.huiji_kb.loops import forecast_enemy, format_loop_forecast
        from plugins.sts2.huiji_kb.store import lookup_enemy
        from plugins.sts2.wiki_enemy import normalize_enemy_wiki_id

        for e in enemies:
            if int((e or {}).get("hp", 0) or 0) <= 0:
                continue
            kb = lookup_enemy(normalize_enemy_wiki_id(e))
            if not kb:
                continue
            fc = forecast_enemy(kb, e, horizon=3)
            bit = format_loop_forecast(fc)
            if bit:
                nm = e.get("name") or kb.get("name_zh") or "?"
                loop_bits.append(f"  {nm}: {bit}")
    except Exception:
        pass
    if loop_bits:
        lines.append("预填循环摘要:")
        lines.extend(loop_bits[:4])

    return "\n".join(lines)


def structured_context(state: dict) -> Dict[str, Any]:
    """Machine-readable slice for tools / logging (optional)."""
    st = str(state.get("state_type") or "")
    out: Dict[str, Any] = {
        "state_type": st,
        "layers": ["macro", "game_flow", "compute", "screen", "discipline", "memory"],
    }
    if st in _COMBAT:
        out["survival_snapshot"] = state.get("survival_snapshot")
        out["combat_fsm_changed"] = (state.get("combat_fsm") or {}).get("changed")
    try:
        from plugins.sts2.build_knowledge import detect_archetype_from_catalog

        aid, src = detect_archetype_from_catalog(state)
        out["build_archetype"] = {"id": aid, "source": src}
    except Exception:
        pass
    return out
