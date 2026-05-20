"""Assemble game-flow brief for every screen."""

from __future__ import annotations

from typing import List

from plugins.sts2.game_flow_kb.ascension import (
    ancient_heal_amount,
    format_ascension_block,
    rest_heal_amount,
)
from plugins.sts2.game_flow_kb.hand_turn_plan import format_hand_turn_plan
from plugins.sts2.game_flow_kb.merchant import format_merchant_brief
from plugins.sts2.game_flow_kb.wiki_rules import (
    format_boss_brief,
    format_elite_brief,
    format_event_brief,
    format_neow_brief,
    format_potions_brief,
    format_relic_catalog_brief,
    format_rewards_brief,
    format_treasure_brief,
)
from plugins.sts2.game_flow_kb.store import (
    ancients_data,
    kb_version,
    map_data,
    screens_data,
)


def _run_summary(state: dict) -> str:
    run = state.get("run") or {}
    parts: List[str] = []
    for k, label in (
        ("character", "角色"),
        ("act", "幕"),
        ("floor", "层"),
        ("gold", "金"),
    ):
        if run.get(k) is not None:
            parts.append(f"{label}{run[k]}")
    return " · ".join(parts)


def _screen_flow_hint(state: dict) -> str:
    st = str(state.get("state_type") or "")
    scr = (screens_data().get("screens") or {}).get(st) or {}
    layer = scr.get("brief_layer", "")
    acts = scr.get("actions") or []
    lines = [f"【界面·{st}】流程层={layer}"]
    if acts:
        lines.append("  合法动作: " + ", ".join(acts))
    if st == "rest_site":
        rh = rest_heal_amount(state)
        lines.append(
            f"  营火休息预估: +{rh['heal']}HP ({rh['hp_before']}→{rh['hp_after']}/{rh['max_hp']})"
            + (f" +{rh['max_hp_gain']}最大生命" if rh.get("max_hp_gain") else "")
        )
        lines.append("  wiki: 休息=30%最大生命(向下取整)；满血也可休息")
    if st == "event":
        evb = format_event_brief(state)
        if evb:
            lines.append(evb.replace("【事件·wiki】", "  事件:"))
        ev = state.get("event") or {}
        name = str(ev.get("event_name") or ev.get("event_id") or "").lower()
        if any(x in name for x in ("neow", "涅奥")):
            nb = format_neow_brief(state)
            if nb:
                lines.append(nb.replace("【涅奥·wiki】", "  涅奥:"))
        if any(x in name for x in ("ancient", "先古", "orobas", "pael")):
            ah = ancient_heal_amount(state)
            lines.append("  【先古遭遇】须三选一，不可跳过")
            if ah["missing"] > 0:
                lines.append(
                    f"  若选项为补满缺失生命: 预估+{ah['heal']}HP (缺失{ah['missing']}×{ah['ratio']:.0%})"
                    + (f" [{ah['ascension_note']}]" if ah.get("ascension_note") else "")
                )
    if st == "map":
        nodes = (map_data().get("node_types") or {})
        lines.append("  节点: " + " | ".join(
            f"{k}={v.get('name_zh')}" for k, v in list(nodes.items())[:6]
        ))
    if st in ("shop", "merchant", "fake_merchant"):
        mb = format_merchant_brief(state)
        if mb:
            lines.append(mb.replace("【商人·wiki 知识库】", "  商人:"))
    if st == "elite":
        eb = format_elite_brief(state)
        if eb:
            lines.extend(eb.split("\n"))
    if st == "boss":
        bb = format_boss_brief(state)
        if bb:
            lines.append(bb.replace("【Boss·wiki】", "  Boss:"))
    if st in ("treasure", "fake_merchant"):
        tb = format_treasure_brief(state)
        if tb:
            lines.append(tb.replace("【宝箱·wiki】", "  宝箱:"))
    if st in ("card_reward", "card_select", "rewards"):
        rb = format_rewards_brief(state)
        if rb:
            lines.append(rb.replace("【奖励屏·wiki】", "  奖励:"))
    if st in ("relic_select", "relic_select_boss", "treasure"):
        rc = format_relic_catalog_brief(state)
        if rc:
            lines.append(rc.replace("【遗物规则·wiki】", "  遗物:"))
    # 药水栏提示（战斗/非战斗均可能有瓶）
    pb = format_potions_brief(state)
    if pb and st in ("monster", "elite", "boss", "shop", "rest_site"):
        lines.append(pb.replace("【药水·wiki】", "  药水:"))
    return "\n".join(lines)


def _ancient_act_hint(state: dict) -> str:
    run = state.get("run") or {}
    try:
        act = int(run.get("act") or 1)
    except (TypeError, ValueError):
        act = 1
    pool = (ancients_data().get("act_ancients") or {}).get(str(act)) or []
    if not pool:
        return ""
    names = (ancients_data().get("names_zh") or {})
    zh = [names.get(p, p) for p in pool]
    return f"【先古·幕{act}池】可能: {', '.join(zh)}"


def format_game_flow_brief(state: dict) -> str:
    if not state:
        return ""
    parts: List[str] = [
        f"【游戏流程知识库 v{kb_version()}】",
        _run_summary(state),
        format_ascension_block(state),
        _ancient_act_hint(state),
        _screen_flow_hint(state),
    ]
    ht = format_hand_turn_plan(state)
    if ht:
        parts.append(ht)
    return "\n\n".join(p for p in parts if p)
