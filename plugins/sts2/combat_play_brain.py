"""Combat decisions: Wiki + lessons + situation → LLM; scorer fallback."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from plugins.sts2.combat_brain import (
    combat_should_end_turn,
    combat_should_wait,
    incoming_attack_damage,
    is_safe_from_incoming,
)
from plugins.sts2.knowledge import fetch_and_store, get_entry, has_entry
from plugins.sts2.visibility import describe_situation

logger = logging.getLogger(__name__)

_COMBAT = frozenset({"monster", "elite", "boss"})


def _parse_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _hand_cards(state: dict) -> List[dict]:
    return list((state.get("player") or {}).get("hand") or [])


def _enemy_brief(state: dict) -> str:
    lines: List[str] = []
    for e in (state.get("battle") or {}).get("enemies") or []:
        if not isinstance(e, dict):
            continue
        name = e.get("name") or e.get("id") or "?"
        hp = e.get("hp", "?")
        intents = e.get("intents") or []
        itxt = ""
        if intents and isinstance(intents[0], dict):
            it = intents[0]
            itxt = f"{it.get('type', '?')}/{it.get('label', '?')}"
        eid = e.get("entity_id", "")
        lines.append(f"  {name} HP{hp} 意图:{itxt} id={eid}")
    incoming = incoming_attack_damage((state.get("battle") or {}).get("enemies") or [])
    p = state.get("player") or {}
    try:
        block = int(p.get("block", 0))
        hp = int(p.get("hp", p.get("current_hp", 0)))
    except (TypeError, ValueError):
        block, hp = 0, 0
    return (
        "敌人:\n"
        + ("\n".join(lines) if lines else "  (无)")
        + f"\n预计受击≈{incoming} | 格挡={block} HP={hp}"
    )


def _enemy_wiki_brief(state: dict) -> str:
    """Wiki-backed enemy mechanics (not hardcoded heuristics)."""
    from plugins.sts2.wiki_enemy import format_enemy_wiki_lines

    return format_enemy_wiki_lines(state)


def _prefetch_hand_wiki(hand: List[dict], max_fetch: int) -> List[str]:
    from plugins.sts2.config import load_sts2_config

    cfg = load_sts2_config()
    if not cfg.get("study_combat_wiki_first", True):
        return []
    use_llm = bool(cfg.get("knowledge_use_llm", False))
    fetched: List[str] = []
    budget = max(0, int(max_fetch))
    for c in hand:
        if budget <= 0:
            break
        cid = str(c.get("id") or "").strip().upper()
        if not cid or has_entry("cards", cid):
            continue
        ent, _ = fetch_and_store(
            "cards", cid, query=str(c.get("name") or cid), use_llm=use_llm
        )
        if ent:
            fetched.append(cid)
            budget -= 1
    return fetched


def _hand_wiki_block(hand: List[dict]) -> str:
    lines: List[str] = []
    for c in hand:
        cid = str(c.get("id") or "").upper()
        idx = c.get("index", "?")
        ent = get_entry("cards", cid) if cid else None
        playable = "可出" if c.get("can_play") else "禁"
        cost = c.get("cost", "?")
        base = f"[{idx}] {c.get('name') or cid} ({cost}) {playable}"
        if ent:
            tags = ",".join(ent.get("tags") or []) or "?"
            rule = str(ent.get("rule") or "")[:100]
            lines.append(f"{base} | {tags} | {rule}")
        else:
            lines.append(base)
    return "手牌:\n" + ("\n".join(lines) if lines else "  (空)")


def rule_combat_fallback(state: dict) -> Tuple[str, dict, bool]:
    from plugins.sts2.combat_brain import decide_combat
    from plugins.sts2.visibility import describe_action

    body = decide_combat(state, apply_lessons=True)
    return f"规则战斗: {describe_action(state, body)}", body, True


def decide_combat_play(
    state: dict,
    *,
    memory: str = "",
) -> Tuple[str, dict, bool]:
    """LLM combat with wiki + lessons; fallback to combat_scorer."""
    from plugins.sts2.config import load_sts2_config

    cfg = load_sts2_config()
    if not cfg.get("study_combat_play_llm", True):
        comm, body, _ok = rule_combat_fallback(state)
        return comm, body, True

    if combat_should_wait(state):
        return "战斗等待动画", {"action": "__wait__"}, True

    if combat_should_end_turn(state) and not _hand_cards(state):
        return "无手牌，结束回合", {"action": "end_turn"}, True

    if cfg.get("study_combat_rule_shortcuts", False):
        return _combat_rule_shortcuts(state, cfg, memory)

    hand = _hand_cards(state)
    return _combat_llm_turn(state, cfg, memory, hand)


def _combat_rule_shortcuts(
    state: dict, cfg: dict, memory: str
) -> Tuple[str, dict, bool]:
    """Legacy heuristics before LLM (off by default)."""
    from plugins.sts2.combat_brain import (
        prefer_block_play,
        try_lethal_attack,
    )
    from plugins.sts2.combat_resources import prefer_bloodletting_play, prefer_potion_play
    from plugins.sts2.visibility import describe_action

    potion = prefer_potion_play(state)
    if potion:
        return (
            "低血/危急 → 先用药\n"
            f"▶ {describe_action(state, potion)}",
            potion,
            True,
        )

    bleed = prefer_bloodletting_play(state)
    if bleed:
        return (
            "放血线 → 先打 Bloody\n"
            f"▶ {describe_action(state, bleed)}",
            bleed,
            True,
        )

    urgent_block = prefer_block_play(state)
    if urgent_block:
        return (
            "Incoming 高伤 → 先格挡；勿 end_turn 裸吃\n"
            f"▶ {describe_action(state, urgent_block)}",
            urgent_block,
            True,
        )

    lethal = try_lethal_attack(state)
    if lethal:
        return (
            f"可斩杀 → 集火\n▶ {describe_action(state, lethal)}",
            lethal,
            True,
        )

    p0 = state.get("player") or {}
    try:
        hp0 = int(p0.get("hp", 0))
        mx0 = int(p0.get("max_hp", 80) or 80)
        blk0 = int(p0.get("block", 0))
    except (TypeError, ValueError):
        hp0, mx0, blk0 = 0, 80, 0
    inc_arm = incoming_attack_damage((state.get("battle") or {}).get("enemies") or [])
    safe_arm = is_safe_from_incoming(inc_arm, blk0, hp0) and hp0 >= mx0 * 0.35
    if safe_arm or inc_arm == 0:
        for c in _hand_cards(state):
            if not c.get("can_play"):
                continue
            cid = str(c.get("id", "")).upper()
            name = str(c.get("name", ""))
            if cid == "ARMAMENTS" or name == "武装":
                body = {"action": "play_card", "card_index": c.get("index", 0)}
                up_hint = ""
                try:
                    from plugins.sts2.upgrade_advisor import rank_upgrade_candidates

                    hand = _hand_cards(state)
                    ranked = rank_upgrade_candidates(hand, state, limit=1)
                    if ranked:
                        c0, sc, note = ranked[0]
                        up_hint = (
                            f" 升级建议 index={c0.get('index')} "
                            f"{c0.get('name')} (分{sc:.0f}) — {note}"
                        )
                except Exception:
                    pass
                return (
                    "安全窗 → 先升级/武装再输出"
                    f"{up_hint}\n"
                    f"▶ {describe_action(state, body)}",
                    body,
                    True,
                )

    hand = _hand_cards(state)
    return _combat_llm_turn(state, cfg, memory, hand)


def _combat_llm_turn(
    state: dict, cfg: dict, memory: str, hand: List[dict]
) -> Tuple[str, dict, bool]:
    wiki_budget = max(
        0, int(cfg.get("study_combat_play_wiki_max_fetches", 4))
    )
    fetched = _prefetch_hand_wiki(hand, wiki_budget)

    from plugins.sts2.lessons import lessons_for_combat

    lessons = lessons_for_combat(state)
    lesson_txt = "\n".join(f"- {x}" for x in lessons) if lessons else "- (无)"

    battle = state.get("battle") or {}
    turn = battle.get("turn", "?")
    rnd = battle.get("round", "?")

    p = state.get("player") or {}
    try:
        hp_r = int(p.get("hp", 0)) / max(1, int(p.get("max_hp", 80)))
    except (TypeError, ValueError):
        hp_r = 1.0
    low_hp_note = ""
    if hp_r < 0.2:
        low_hp_note = (
            f"\n【低血】HP≈{int(hp_r * 100)}%：优先格挡/用药，"
            "勿贪输出；必要时 end_turn 保留资源。\n"
        )

    p0 = state.get("player") or {}
    try:
        blk = int(p0.get("block", 0))
        hp0 = int(p0.get("hp", 0))
    except (TypeError, ValueError):
        blk, hp0 = 0, 0
    inc0 = incoming_attack_damage((state.get("battle") or {}).get("enemies") or [])
    safe_note = ""
    try:
        mx0 = int(p0.get("max_hp", 80) or 80)
    except (TypeError, ValueError):
        mx0 = 80
    hp_ratio = hp0 / max(1, mx0)
    if is_safe_from_incoming(inc0, blk, hp0) and hp_ratio >= 0.35 and inc0 > 0:
        safe_note = (
            f"\n【相对安全】预计受击≈{inc0}，格挡={blk}+HP{hp0} — "
            "可规划输出，但仍须按意图循环留格挡。\n"
        )
    elif inc0 == 0:
        safe_note = (
            "\n【无攻击意图】可能是 Buff/Debuff/Stun — 可读条后输出或攒资源。\n"
        )

    from plugins.sts2.run_objective import llm_run_objective_system

    system = (
        "你是 STS2 战斗教练：先读 Wiki/机制，再出牌。"
        + llm_run_objective_system()
        + "\n要求：commentary 引用 Wiki 或意图；JSON 仅含 action 等字段。"
        "\n动作: play_card(card_index,target) | end_turn | use_potion | __wait__"
        f"{low_hp_note}{safe_note}"
        'JSON: {"commentary":"...","action":"play_card|end_turn|use_potion|__wait__",'
        '"card_index":0,"target":"ENTITY_ID"}'
        "\n非法时优先 __wait__；无牌可打则 end_turn。"
    )
    from plugins.sts2.thinking_policy import combat_system_append

    system += combat_system_append()

    from plugins.sts2.knowledge_pack import assemble_combat_pack

    user = assemble_combat_pack(state, hand, memory=memory, prefetched_wiki=fetched)
    brief = str(state.get("_decision_brief") or "").strip()
    if brief:
        user += f"\n\n【决策简报】\n{brief[:4500]}"
    user += f"\n\n回合: {rnd} ({turn})"
    if lesson_txt and lesson_txt != "- (无)":
        user += f"\n\n教训:\n{lesson_txt}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        from plugins.sts2.llm_util import sts2_call_llm
        from plugins.sts2.thinking_policy import commentary_substantive, llm_retry_user

        raw = sts2_call_llm(
            messages,
            max_tokens=int(cfg.get("study_combat_play_max_tokens", 900)),
            temperature=float(cfg.get("study_combat_play_temperature", 0.35)),
        )
        parsed_probe = _parse_json(raw)
        comm_probe = str((parsed_probe or {}).get("commentary") or "")
        if parsed_probe and not commentary_substantive(comm_probe, combat=True):
            raw2 = sts2_call_llm(
                messages
                + [
                    {"role": "assistant", "content": raw[:800]},
                    {"role": "user", "content": llm_retry_user("战斗 commentary 过短")},
                ],
                max_tokens=int(cfg.get("study_combat_play_max_tokens", 900)),
                temperature=float(cfg.get("study_combat_play_temperature", 0.35)),
            )
            if raw2:
                raw = raw2
    except Exception as exc:
        logger.warning("combat_play LLM failed: %s", exc)
        if cfg.get("study_combat_rule_fallback", False):
            comm, body, _ok = rule_combat_fallback(state)
            return comm, body, True
        return (
            f"战斗 LLM 失败: {exc} — 可 play_brief 或手操 sts2_act。",
            {"action": "__pause__"},
            True,
        )

    parsed = _parse_json(raw)
    if not parsed:
        if cfg.get("study_combat_rule_fallback", False):
            comm, body, _ok = rule_combat_fallback(state)
            return comm, body, True
        return (
            "战斗 LLM 未解析 JSON — 请 play_brief 或 sts2_act。",
            {"action": "__pause__"},
            True,
        )

    commentary = str(parsed.pop("commentary", "") or "战斗决策").strip()
    action = str(parsed.get("action") or "").strip()
    body = dict(parsed)
    body["action"] = action

    from plugins.sts2.action_validate import validate_action
    from plugins.sts2.decision import _coerce_action
    from plugins.sts2.visibility import describe_action

    body = validate_action(state, body)
    body = _coerce_action(state, body)
    return f"{commentary}\n▶ {describe_action(state, body)}", body, True


def note_combat_aftermath(
    prev: Optional[dict],
    nxt: dict,
) -> Optional[str]:
    """After leaving combat, record hp swing as a learnable rule."""
    if not prev or not nxt:
        return None
    if str(prev.get("state_type") or "") not in _COMBAT:
        return None
    if str(nxt.get("state_type") or "") in _COMBAT:
        return None
    try:
        php = int((prev.get("player") or {}).get("hp", 0))
        nhp = int((nxt.get("player") or {}).get("hp", 0))
    except (TypeError, ValueError):
        return None
    loss = php - nhp
    if loss < 12:
        return None
    floor = (prev.get("run") or {}).get("floor", "?")
    from plugins.sts2.notes import merge_strategy_rules

    rule = f"第{floor}层战后掉血{loss}：下战优先格挡/用药，勿贪刀。"
    merge_strategy_rules([rule])
    return rule
