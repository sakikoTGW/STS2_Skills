"""Act-level operational brief — HP budget, elite gates, rest/shop hints for LLM."""

from __future__ import annotations

from typing import List

from plugins.sts2.run_objective import _hp_ratio, map_route_objective_lines


def _floor_act(state: dict) -> tuple[int, int]:
    run = state.get("run") or {}
    try:
        return int(run.get("floor") or 0), max(1, int(run.get("act") or 1))
    except (TypeError, ValueError):
        return 0, 1


def format_map_operational_brief(state: dict) -> str:
    """Extra map coaching beyond route stats."""
    floor, act = _floor_act(state)
    hp_pct = int(100 * _hp_ratio(state))
    lines = list(map_route_objective_lines(state))
    lines.append("")
    lines.append("【运营·选路门禁】（LLM 最终拍板，下列为硬提示）")

    if act == 1 and hp_pct < 50:
        lines.append(
            f"  ⛔ HP{hp_pct}%<50%：Act1 禁止精英；ONLY ?/营火/monster 直到>50%。"
        )
    elif act == 1 and floor <= 12 and hp_pct < 72:
        lines.append(
            f"  HP{hp_pct}%<72% 且≤12层：默认不选 elite，优先 monster/?/营火。"
        )
    elif act == 1 and floor <= 9 and hp_pct < 78:
        lines.append(
            f"  HP{hp_pct}%<78% 前9层：非必要不选 elite。"
        )
    if hp_pct >= 75 and floor >= 12:
        lines.append("  血线健康：可考虑精英换遗物，仍算战后 HP 是否够撑到下营火。")

    m = state.get("map") or {}
    opts = m.get("next_options") or state.get("next_options") or []
    for o in opts[:6]:
        if not isinstance(o, dict):
            continue
        typ = str(o.get("type", o.get("symbol", ""))).lower()
        ix = o.get("index")
        if typ == "elite" and hp_pct < 65:
            lines.append(
                f"  index={ix} elite：当前血偏低 → 默认不建议，除非构筑可速杀且战后能活"
            )
        elif typ in ("rest", "rest_site", "campfire"):
            lines.append(f"  index={ix} 营火：低血优先 heal")
    return "\n".join(lines)


def format_global_play_header(state: dict) -> str:
    """Top of every play_brief — who decides."""
    st = str(state.get("state_type") or "")
    lines = [
        "【唯一决策体·主 Agent】目标 FULL_RUN_CLEARED（三幕 Boss）。",
        "sts2_get_state=观测，sts2_act=执行；禁止 sts2_autoplay study/start/step。",
        "play_brief/状态机/生存算数是事实，不是替你出的牌。",
    ]
    if st in ("monster", "elite", "boss"):
        lines.append(
            "战斗：同一玩家回合内多次 get_state→sts2_act 用尽能量；"
            "参考【本回合出牌计划】【组合伤害】，可因教练/抽牌调整。"
        )
    return "\n".join(lines)
