"""Deck-aware card picks: LLM reasoning + skip-to-avoid-bloat fallback."""



from __future__ import annotations



import json

import logging

import re

from collections import Counter

from typing import Any, Dict, List, Optional, Tuple



from plugins.sts2.reward_cards import format_card_offers, offer_reward_cards

from plugins.sts2.visibility import describe_situation



logger = logging.getLogger(__name__)



def summarize_deck(state: dict) -> str:
    """Short deck composition for pick reasoning."""

    cards = _collect_deck_cards(state)

    if not cards:

        return "当前牌组: (API 未返回完整牌组，仅知手牌/场面)"



    counts: Counter[str] = Counter()

    types: Counter[str] = Counter()

    for c in cards:

        rid = str(c.get("id") or c.get("name") or "?")

        counts[rid] += 1

        types[str(c.get("type") or "?").lower()] += 1



    strike_like = sum(

        n

        for k, n in counts.items()

        if "strike" in k.lower() or "打击" in k

    )

    power_like = sum(

        n for k, n in counts.items() if "power" in str(k).lower() or k in _POWER_IDS

    )



    top = counts.most_common(8)

    top_s = ", ".join(f"{k}×{v}" for k, v in top)

    return (

        f"牌组约 {len(cards)} 张引用 | 攻/技/能 {types.get('attack', 0)}/"

        f"{types.get('skill', 0)}/{types.get('power', 0)} | "

        f"打击类≈{strike_like} | 能力牌≈{power_like} | 常见: {top_s}"

    )





_POWER_IDS = frozenset(

    {

        "INFLAME",

        "DEMON_FORM",

        "FEEL_NO_PAIN",

        "DARK_EMBRACE",

        "CORRUPTION",

        "BARRICADE",

        "METALLICIZE",

        "COMBUSTION",

    }

)





def _collect_deck_cards(state: dict) -> list:
    """Extract deck card list from state, handling various formats."""
    try:
        cards = []
        # Try master_deck first
        raw = state.get("master_deck") or state.get("deck") or []
        if isinstance(raw, list):
            for c in raw:
                if isinstance(c, dict):
                    cards.append(c)
        if cards:
            return cards
        # Try player.deck
        player = state.get("player") or {}
        raw2 = player.get("deck") or player.get("master_deck") or []
        if isinstance(raw2, list):
            for c in raw2:
                if isinstance(c, dict):
                    cards.append(c)
        return cards
    except Exception:
        return []



def card_reward_can_skip(state: dict) -> bool:

    """True only when the game exposes an explicit skip/decline — not can_proceed."""

    block = state.get("card_reward") or {}

    return bool(

        block.get("can_skip")

        or block.get("can_decline")

        or block.get("skip_available")

    )





def card_reward_should_skip(state: dict, offers: List[dict]) -> bool:

    """STS2 rewards are curated pools — almost never skip (no STS1 '3 Strikes' spam)."""

    return False





def _archetype_hint(state: dict) -> str:
    """Full build brief for pick/upgrade prompts."""
    try:
        from plugins.sts2.upgrade_advisor import (
            collect_upgrade_candidates,
            format_upgrade_brief,
            is_upgrade_screen,
        )

        if is_upgrade_screen(state):
            cards = collect_upgrade_candidates(state)
            return format_upgrade_brief(state, cards, context="升级选牌")
    except Exception:
        pass
    from plugins.sts2.build_knowledge import format_build_pick_brief

    offers = offer_reward_cards(state)
    return format_build_pick_brief(state, offers)





def rule_card_reward_fallback(state: dict) -> Tuple[str, dict]:

    """Rules + deck pollution heuristics when LLM unavailable."""

    from plugins.sts2.decision import _pick_best_card



    offers = offer_reward_cards(state)

    if not offers:

        if card_reward_can_skip(state) and card_reward_should_skip(state, []):

            return (

                "规则: 牌组打击过多且可跳过 → proceed。",

                {"action": "proceed"},

            )

        return "规则: 列表未同步，默认选 #0。", {

            "action": "select_card_reward",

            "card_index": 0,

        }



    if card_reward_should_skip(state, offers):

        strike_cnt = sum(

            1

            for c in _collect_deck_cards(state)

            if "strike" in str(c.get("id", "")).lower()

            or "打击" in str(c.get("name", ""))

        )

        return (

            f"规则: 牌组已有约 {strike_cnt} 张打击，奖励仍全打击 → 跳过防污染。",

            {"action": "proceed"},

        )



    from plugins.sts2.ironclad_builds import pick_best_offer_index



    idx = pick_best_offer_index(state, offers)

    name = next(

        (c.get("name") or c.get("id") for c in offers if c.get("index") == idx),

        "?",

    )

    return f"规则兜底: 选 #{idx} {name}。", {

        "action": "select_card_reward",

        "card_index": idx,

    }


def card_select_should_confirm(state: dict) -> bool:
    cs = state.get("card_select") or {}
    if cs.get("preview_showing") and cs.get("can_confirm"):
        return True
    return bool(cs.get("can_confirm", False))


def rule_card_select_fallback(state: dict) -> Tuple[str, dict]:
    """Smith / upgrade / transform grid — preview then confirm."""
    from plugins.sts2.decision import _pick_best_card

    cs = state.get("card_select") or {}
    if card_select_should_confirm(state):
        return "规则: 确认升级/选择。", {"action": "confirm_selection"}

    cards = [c for c in (offer_reward_cards(state) or cs.get("cards") or []) if isinstance(c, dict)]
    if not cards:
        if cs.get("preview_showing"):
            return "规则: 预览中无法确认 → 取消重选。", {"action": "cancel_selection"}
        return "规则: 无卡可选 → proceed。", {"action": "proceed"}

    idx = _pick_best_card(cards)
    if idx is None:
        idx = int(cards[0].get("index", 0))
    name = next((c.get("name") or c.get("id") for c in cards if c.get("index") == idx), "?")
    return f"规则: 选 #{idx} {name}。", {"action": "select_card", "index": idx}


def decide_card_reward(

    state: dict,

    *,

    memory: str = "",

) -> Tuple[str, dict, bool]:

    """

    LLM deck-building pick. Returns (commentary, body, ok).

    Supports select_card_reward OR proceed (skip) when allowed.

    """

    from plugins.sts2.config import load_sts2_config
def _parse_json(text: str) -> dict | None:
    """Parse JSON from LLM response, trying various formats."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    import re
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None






    cfg = load_sts2_config()

    if not cfg.get("study_card_pick_llm", True):

        comm, body = rule_card_reward_fallback(state)

        return comm, body, True



    offers = offer_reward_cards(state)

    if not offers:

        if card_reward_can_skip(state) and card_reward_should_skip(state, []):

            comm, body = rule_card_reward_fallback(state)

            return comm, body, True

        return (

            "选卡列表未同步，仍必须拿一张 → 尝试 #0。",

            {"action": "select_card_reward", "card_index": 0},

            True,

        )



    can_skip = card_reward_can_skip(state)

    may_skip = card_reward_should_skip(state, offers)

    deck_line = summarize_deck(state)

    arch = _archetype_hint(state)

    offers_line = format_card_offers(offers)

    situation = describe_situation(state)

    run = state.get("run") or {}

    try:

        floor = int(run.get("floor") or 0)

        act = int(run.get("act") or 1)

    except (TypeError, ValueError):

        floor, act = 0, 1



    from plugins.sts2.wiki_pick_context import build_pick_context



    wiki_ctx = build_pick_context(state, offers=offers)



    if act == 1 and floor < 12:

        skip_hint = (

            "【强制】Act1 前12层必须 select_card_reward 选一张，禁止 proceed 跳过。"

        )

    elif may_skip:

        skip_hint = "仅当三张都是弱打击且牌组打击≥5 时，才可 action=proceed 跳过。"

    elif can_skip:

        skip_hint = "有跳过按钮，但默认仍应选一张补强构筑；只有明显污染时才 proceed。"

    else:

        skip_hint = "本界面不能跳过，必须 select_card_reward 选一张。"



    from plugins.sts2.ironclad_builds import combat_playbook_snippet



    from plugins.sts2.run_objective import llm_run_objective_system

    system = (
        "你是 STS2 构牌教练。第一目的：通关整局；第二目的：控战损；第三：巩固当前构筑主轴。\n"
        + llm_run_objective_system()
        + "必须先读【构筑诊断】+【层级对策】+ Wiki，再决策。\n"
        "commentary：①主轴与缺件 ②各候选对主轴/层级恶心怪的价值 ③对通关战损的影响 ④结论。\n"
        "禁止单卡面板贪心；禁止「都差不多」。\n"
        "默认 select_card_reward；仅 skip_hint 允许时 proceed。\n"
        'JSON: {"commentary":"...", "action":"select_card_reward|proceed", "card_index":0}'
    )

    user = (

        f"{wiki_ctx}\n\n---\n{arch}\n\n{combat_playbook_snippet(state)}\n\n"

        f"{situation}\n{deck_line}\n{offers_line}\n\n"

        f"{skip_hint}\n\nCandidates:\n{json.dumps(offers, ensure_ascii=False)[:3000]}\n"

    )

    if memory:

        user += f"\n本局备注:\n{memory[:1200]}\n"



    try:

        from plugins.sts2.llm_util import sts2_call_llm



        raw = sts2_call_llm(

            [

                {"role": "system", "content": system},

                {"role": "user", "content": user},

            ],

            max_tokens=int(cfg.get("study_card_pick_max_tokens", 720)),

            temperature=float(cfg.get("study_card_pick_temperature", 0.35)),

        )

    except Exception as exc:

        logger.warning("card_pick LLM failed: %s", exc)

        comm, body = rule_card_reward_fallback(state)

        return comm, body, True



    parsed = _parse_json(raw)

    if not parsed:

        comm, body = rule_card_reward_fallback(state)

        return comm, body, True



    commentary = str(parsed.pop("commentary", "") or "构牌决策。").strip()

    action = str(parsed.get("action") or "").strip()

    

    body = dict(parsed)

    body["action"] = action



    if action == "confirm_selection":

        cs = state.get("card_select") or {}

        if not cs.get("can_confirm"):

            # LLM wants confirm but game says no - pick card instead

            from plugins.sts2.decision import _pick_best_card

            cards2 = offer_reward_cards(state)

            if cards2:

                i2 = _pick_best_card(cards2)

                if i2 is not None:
                    # can_confirm=False but LLM wants confirm - pick card first
                    idx2 = i2
                    from plugins.sts2.visibility import describe_action
                    return (
                        f"{commentary} [auto-fix] can_confirm=False, picking #" + str(idx2) + "",
                        {"action": "select_card", "index": idx2},
                        True,
                    )

        from plugins.sts2.visibility import describe_action

        return f"{commentary}" + chr(10) + chr(9654) + " " + describe_action(state, body), body, True




    if action == "proceed":
        comm, body = rule_card_select_fallback(state)
        return comm, body, True

    from plugins.sts2.action_validate import validate_action

    from plugins.sts2.decision import _coerce_action



    body = validate_action(state, body)

    body = _coerce_action(state, body)

    from plugins.sts2.visibility import describe_action



    return f"{commentary}" + chr(10) + chr(9654) + chr(32) + describe_action(state, body), body, True

