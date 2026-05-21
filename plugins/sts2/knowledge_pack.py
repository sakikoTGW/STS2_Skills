"""Wiki + deck-build + macro strategy — one pack injected into every LLM step."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_GUIDE_PATH = Path(__file__).resolve().parent / "references" / "sts2_ironclad_guide.md"


@lru_cache(maxsize=1)
def ironclad_guide_excerpt(*, max_chars: int = 2200) -> str:
    try:
        text = _GUIDE_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    text = text.strip()
    if len(text) > max_chars:
        return text[:max_chars] + "\n…(铁甲指南截断，完整见 references/sts2_ironclad_guide.md)"
    return text


def _char_is_ironclad(state: dict) -> bool:
    run = state.get("run") or {}
    p = state.get("player") or {}
    for k in ("character", "class", "character_id"):
        v = str(run.get(k) or p.get(k) or "").upper()
        if "IRON" in v:
            return True
    return True  # default ironclad study profile


def macro_strategy_block(state: dict) -> str:
    """Run goal + build diagnosis — must appear before micro tactics."""
    parts: list[str] = []
    try:
        from plugins.sts2.run_objective import format_run_objective_block

        parts.append(format_run_objective_block(state))
    except Exception:
        pass
    try:
        if _char_is_ironclad(state):
            from plugins.sts2.ironclad_builds import build_strategy_brief

            parts.append(build_strategy_brief(state))
        else:
            from plugins.sts2.build_knowledge import format_build_pick_brief

            parts.append(format_build_pick_brief(state))
    except Exception:
        pass
    try:
        from plugins.sts2.build_knowledge import format_layer_threat_block

        layer = format_layer_threat_block(state)
        if layer:
            parts.append(layer)
    except Exception:
        pass
    guide = ironclad_guide_excerpt()
    if guide and _char_is_ironclad(state):
        parts.append("【铁甲构筑参考·摘录】\n" + guide)
    return "\n\n".join(p for p in parts if p)


def wiki_combat_block(state: dict, hand: list[dict], *, prefetched: list[str] | None = None) -> str:
    from plugins.sts2.combat_play_brain import (
        _enemy_wiki_brief,
        _hand_wiki_block,
        _prefetch_hand_wiki,
    )
    from plugins.sts2.config import load_sts2_config

    cfg = load_sts2_config()
    budget = max(0, int(cfg.get("study_combat_wiki_max_fetches", 6)))
    fetched = prefetched if prefetched is not None else _prefetch_hand_wiki(hand, budget)
    lines: list[str] = ["【Wiki·战斗必读】先读怪物行为与手牌词条，再定本动。"]
    ew = _enemy_wiki_brief(state)
    if ew:
        lines.append(ew)
    hw = _hand_wiki_block(hand)
    if hw:
        lines.append(hw)
    if fetched:
        lines.append(f"本回合新查 Wiki 卡: {', '.join(fetched)}")
    lines.append(
        "commentary 须引用至少一处 Wiki/机制（敌人意图循环或卡牌词条），并说明【构筑】主轴。"
    )
    return "\n".join(lines)


def wiki_pick_block(state: dict, *, offers: list[dict] | None = None) -> str:
    from plugins.sts2.wiki_pick_context import build_pick_context

    return build_pick_context(state, offers=offers)


def assemble_combat_pack(
    state: dict,
    hand: list[dict],
    *,
    memory: str = "",
    prefetched_wiki: list[str] | None = None,
) -> str:
    """Combat LLM user message: same L0/L1 order as agent play_brief."""
    try:
        from plugins.sts2.decision_context import layer_compute, layer_macro

        head = "\n\n".join(
            x for x in (layer_macro(state), layer_compute(state)) if x
        )
    except Exception:
        head = macro_strategy_block(state)
    parts: list[str] = [head, wiki_combat_block(state, hand, prefetched=prefetched_wiki)]
    try:
        from plugins.sts2.build_knowledge import format_build_combat_hint

        parts.append(format_build_combat_hint(state))
    except Exception:
        pass
    try:
        from plugins.sts2.combat_line_planner import format_line_plan_block

        blk = format_line_plan_block(state)
        if blk:
            parts.append(blk)
    except Exception:
        pass
    try:
        from plugins.sts2.combat_turn_plan import format_turn_plan_block

        blk = format_turn_plan_block(state)
        if blk:
            parts.append(blk)
    except Exception:
        pass
    try:
        from plugins.sts2.combat_play_brain import _enemy_brief
        from plugins.sts2.wiki_pick_context import situation_context

        parts.append(situation_context(state))
        parts.append(_enemy_brief(state))
    except Exception:
        pass
    try:
        from plugins.sts2.lessons import lessons_for_combat

        les = lessons_for_combat(state)
        if les:
            parts.append("跨局教训:\n" + "\n".join(f"- {x}" for x in les))
    except Exception:
        pass
    if memory:
        parts.append(f"本局记忆:\n{memory[:1500]}")
    return "\n\n".join(p for p in parts if p)


def assemble_decide_pack(state: dict, *, offers: list[dict] | None = None) -> str:
    """Map / reward / event / rest — wiki + 构筑 + route."""
    st = str(state.get("state_type") or "")
    parts: list[str] = [macro_strategy_block(state)]

    if st == "map":
        try:
            from plugins.sts2.map_route_learn import format_map_route_brief

            route = format_map_route_brief(state)
            if route:
                parts.append(route)
        except Exception:
            pass
        parts.append(
            "【地图思路】按 Act 通关+控战损选路；精英仅在构筑/血线支持时；"
            "commentary 须写清①当前主轴②本格风险③选路理由。"
        )

    if st in ("card_reward", "card_select"):
        try:
            from plugins.sts2.build_knowledge import format_build_pick_brief
            from plugins.sts2.reward_cards import offer_reward_cards

            off = offers if offers is not None else offer_reward_cards(state)
            parts.append(format_build_pick_brief(state, off))
            parts.append(wiki_pick_block(state, offers=off))
        except Exception:
            pass
    elif st in ("relic_select", "relic_select_boss", "treasure", "fake_merchant"):
        try:
            from plugins.sts2.wiki_pick_context import situation_context

            parts.append(situation_context(state))
            parts.append(
                "【遗物思路】服务当前构筑主轴与层级对策；commentary 写取舍，勿只看单遗物强度。"
            )
        except Exception:
            pass
    elif st == "rewards":
        try:
            from plugins.sts2.rewards_screen import format_rewards_brief

            parts.append(format_rewards_brief(state))
        except Exception:
            pass
    elif st == "rest_site":
        try:
            from plugins.sts2.upgrade_advisor import format_rest_site_brief

            parts.append(format_rest_site_brief(state))
        except Exception:
            pass
    elif st == "event":
        parts.append(
            "【事件思路】优先通关与血线；commentary 写选项对构筑/战损的影响，勿瞎赌。"
        )
    else:
        if _char_is_ironclad(state):
            guide = ironclad_guide_excerpt(max_chars=1200)
            if guide:
                parts.append(guide)

    try:
        from plugins.sts2.notes import recall_block

        recall = recall_block()
        if recall:
            parts.append(recall[:2000])
    except Exception:
        pass

    parts.append(
        "【输出要求】commentary 必须同时提到：构筑主轴（或缺件）+ 本屏决策理由；"
        "涉及卡牌/怪物时引用上文 Wiki，禁止臆测未给出的效果。"
    )
    return "\n\n".join(p for p in parts if p)
