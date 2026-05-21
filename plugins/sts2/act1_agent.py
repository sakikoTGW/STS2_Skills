"""Act1 agent-play coaching — map gates, mission banner, suggested actions."""

from __future__ import annotations

import json

from plugins.sts2.act1_clear import hp_ratio, map_node_score, pick_map_node, run_floor


def run_act(state: dict | None) -> int:
    if not state:
        return 1
    try:
        from plugins.sts2.run_victory import run_act as _ra

        return int(_ra(state))
    except Exception:
        run = state.get("run") or {}
        try:
            return max(1, int(run.get("act") or 1))
        except (TypeError, ValueError):
            return 1


def act1_agent_play() -> bool:
    try:
        from plugins.sts2.play_mode import agent_play_mode

        return agent_play_mode() and run_act({}) == 1
    except Exception:
        return False


def format_act1_mission_banner(state: dict) -> str:
    """Top-of-brief Act1 contract when agent-play is on."""
    if run_act(state) != 1:
        return ""
    floor = run_floor(state)
    ratio = hp_ratio(state)
    hp_pct = int(100 * ratio)
    lines = [
        "【Act1 通关任务·本改动唯一目标】",
        "必须打通第一幕 Boss（FULL_ACT1_CLEARED），禁止送死式贪精英/乱 end_turn。",
        f"  当前 第{floor}层 HP{hp_pct}%",
        "  铁律：HP<50% 绝不进精英；前12层 HP<72% 不进精英；有营火且 HP<75% 优先营火。",
        "  战斗：读【生存闸门】与 T+0~T+2 意图；高伤回合先叠防/用药；多怪先杀最高伤意图怪。",
        "  精英幽灵鳗：读【怪物Wiki】Skittish(每回合首次受击格挡)，勿瞎猜「怕小」。",
        "  工具：禁止 sts2_autoplay study/start/step；每动前 get_state(summary=true)。",
    ]
    if ratio < 0.5:
        lines.append("  ⛔ 血线危险：下一路 ONLY ?/营火/普通战，直到回血。")
    elif floor <= 12 and ratio < 0.72:
        lines.append("  ⚠ 前段低血：跳过精英，优先 monster/?/营火。")
    return "\n".join(lines)


def suggested_map_action(state: dict) -> dict | None:
    """Code-suggested map pick for agent (not forced POST)."""
    if str(state.get("state_type") or "") != "map":
        return None
    m = state.get("map") or {}
    opts = m.get("next_options") or state.get("next_options") or []
    if not opts:
        return None
    body = pick_map_node(opts, state)
    return body


def format_act1_map_coaching(state: dict) -> str:
    if str(state.get("state_type") or "") != "map":
        return ""
    m = state.get("map") or {}
    opts = [o for o in (m.get("next_options") or state.get("next_options") or []) if isinstance(o, dict)]
    if not opts:
        return ""
    ratio = hp_ratio(state)
    floor = run_floor(state)
    hp_pct = int(100 * ratio)
    ranked = sorted(opts, key=lambda o: map_node_score(o, state))
    best = ranked[0]
    lines = [
        f"【Act1 选路·代码推荐】HP{hp_pct}% 第{floor}层（分数越低越优）",
    ]
    for o in ranked[:5]:
        ix = o.get("index", "?")
        typ = o.get("type", o.get("symbol", "?"))
        sc = map_node_score(o, state)
        mark = " ★推荐" if o is best else ""
        if "elite" in str(typ).lower() and (ratio < 0.5 or (floor < 12 and ratio < 0.72)):
            mark = " ⛔禁止"
        lines.append(f"  index={ix} {typ} score={sc}{mark}")
    sug = suggested_map_action(state)
    if sug:
        lines.append(
            "  → mandatory_next_action: "
            + json.dumps(sug, ensure_ascii=False)
        )
    return "\n".join(lines)


def attach_act1_agent_fields(payload: dict) -> dict:
    if not isinstance(payload, dict) or run_act(payload) != 1:
        return payload
    try:
        from plugins.sts2.play_mode import agent_play_mode

        if not agent_play_mode():
            return payload
    except Exception:
        return payload

    out = dict(payload)
    out["act1_mission"] = "FULL_ACT1_CLEAR"
    banner = format_act1_mission_banner(payload)
    if banner:
        out["act1_coaching"] = banner
    st = str(payload.get("state_type") or "")
    if st == "map":
        coach = format_act1_map_coaching(payload)
        if coach:
            out["act1_map_coaching"] = coach
        sug = suggested_map_action(payload)
        if sug:
            out["mandatory_next_action"] = sug
    return out
