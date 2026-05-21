"""Agent-play architecture — interactive coach + on-demand LLM autopilot."""

from __future__ import annotations

_BRIEF_STRIP_MARKERS = (
    "规则引擎建议",
    "LLM出牌建议",
    "建议动作:",
    "【强制下一动】",
    "【状态机·LLM",
    "评分战斗",
    "通关模式】",
    "代码推荐",
    "mandatory_next_action",
)


def agent_sole_decider() -> bool:
    try:
        from plugins.sts2.play_mode import agent_play_mode, autopilot_active

        return agent_play_mode() and not autopilot_active()
    except Exception:
        return False


def format_agent_contract(state: dict) -> str:
    """Contract on every get_state — who decides and how to control autopilot."""
    st = str(state.get("state_type") or "")
    fsm = state.get("combat_fsm") or {}
    try:
        from plugins.sts2.play_mode import autopilot_active

        ap_running = autopilot_active()
    except Exception:
        ap_running = False

    if ap_running:
        lines: list[str] = [
            "【架构·一口气代打中 — 你不要自己出牌】",
            "后台线程在自动通关；你=教练/解说，除非用户说「停」。",
            "禁止: 用 sts2_act 抢操作（会 pause 代打）；禁止问「继续吗」。",
            "用户说停/stop → sts2_autoplay action=stop；战术 → action=hint。",
            "status 看进度；resume 仅 pause 之后。",
        ]
        return "\n".join(lines)

    try:
        from plugins.sts2.play_mode import mount_mode

        if mount_mode():
            lines = [
                "【架构·挂载模式 — 主 Agent 边聊边打，禁止后台代打】",
                "唯一链路：sts2_ping → sts2_get_state(summary=true) → sts2_act → 循环。",
                "禁止：sts2_autoplay(run/status 也别用来代替打牌)、terminal、search_files、",
                "read_file、execute_code、自写 Python/HTTP 访问游戏。",
                "sts2_setup_status 最多 1 次；之后必须 get_state+act。",
                "用户说「打吧/开打/继续通关」：同一轮内连续 tool 直到 FULL_RUN_CLEARED。",
                "可边聊，禁止问「继续吗」；仅用户说「停」才停。",
                "ping 失败：说明请开 STS2+STS2_MCP 模组，不要猜端口写脚本。",
                "战斗：读 combat_fsm 五区快照；think_required=1 时须深度思考后再 sts2_act。",
                "思考必填六项：意图 | 净入伤/格挡 | 行为循环 T+1/T+2 | 本动目标 | 取舍 | 构筑主轴。",
                "combat_think 为辅脑参考，可吸收但禁止照抄；你仍是唯一决策者。",
                "本回合多张 sts2_act 后再 end_turn；读 play_brief / legal_actions。",
            ]
            try:
                from plugins.sts2.mode_display import format_mode_banner

                lines.insert(0, format_mode_banner(compact=True))
            except Exception:
                pass
            return "\n".join(lines)
    except Exception:
        pass

    try:
        from plugins.sts2.mode_display import auto_run_env_enabled, resolve_sts2_mode

        m = resolve_sts2_mode()
        if auto_run_env_enabled() and m.get("mode_id") == "autopilot_ready":
            lines: list[str] = [
                "【架构·AUTO_RUN 待启动】",
                "一口气代打尚未 run：游戏连上后会自动开，或你立刻 sts2_autoplay action=run。",
                "禁止用 sts2_act 边聊边打代替代打（除非用户明确要手操）。",
                "启动后你会变教练模式；用户说「停」才 stop。",
            ]
            try:
                from plugins.sts2.mode_display import format_mode_banner

                lines.insert(0, format_mode_banner(compact=True))
            except Exception:
                pass
            return "\n".join(lines)
    except Exception:
        pass

    try:
        from plugins.sts2.mode_display import format_mode_banner

        mode_hdr = format_mode_banner(compact=True)
    except Exception:
        mode_hdr = ""

    lines: list[str] = []
    if mode_hdr:
        lines.append(mode_hdr)
    lines.extend(
        [
        "【架构·交互模式】",
        "默认由你（主 Agent）决策：sts2_get_state → 思考 → sts2_act。",
        "用户说「开始代打/帮我打」→ sts2_autoplay action=run（LLM 后台代打至通关）。",
        "代打中仍可聊天；stop/pause/hint 控制代打，sts2_act 可暂停后手操。",
        "play_brief 分层：L0构筑 → L1算数/循环 → L2本屏 → L3纪律；按顺序读。",
        "目标：FULL_RUN_CLEARED（Act1→Act2→Act3 Boss）。",
        "",
        "【每步（手操时）】",
        "1) sts2_get_state(summary=true)",
        "2) 按【思考模板】写回复（战斗：净入伤+循环+本动理由）",
        "3) sts2_act；战斗同一回合可多张牌，再 end_turn",
    ]
    )
    if fsm.get("think_required"):
        zones = ", ".join(fsm.get("changed_zones") or [])
        lines.append(f"4) 状态机已变: {zones} — 必须根据新快照重想")
    if st in ("monster", "elite", "boss", "hand_select"):
        lines.extend(
            [
                "战斗：读 combat_fsm + survival_snapshot；勿盲跟旧计划。",
                "【禁止半道收工】战斗未结束（state 仍为战斗屏）时：",
                "  - 禁止只写「end_turn」而不 sts2_act；禁止输出长篇进度表后问用户「继续吗」。",
                "  - 本回合牌打完 → 必须 tool 调用 end_turn → 再 get_state → 继续出牌直到胜/地图。",
                "  - 同一轮对话内连续 tool，直到离开战斗；只有用户明确说停才停。",
            ]
        )
    elif st == "map":
        lines.append("地图：你自己选 index；Act1 低血时勿进精英（见 play_brief）。")
    return "\n".join(lines)


def sanitize_payload_for_agent(payload: dict) -> dict:
    """Remove substitute-decision text when main agent is sole decider."""
    if not agent_sole_decider() or not isinstance(payload, dict):
        return payload
    out = dict(payload)
    if out.get("mandatory_next_action") is not None:
        out["coach_hint"] = out.pop("mandatory_next_action")
    pb = str(out.get("play_brief") or "")
    if pb:
        kept = [
            ln
            for ln in pb.splitlines()
            if not any(m in ln for m in _BRIEF_STRIP_MARKERS)
        ]
        out["play_brief"] = "\n".join(kept)
    out["agent_contract"] = format_agent_contract(out)
    out["sole_decider"] = "main_agent"
    out["substitute_brains_disabled"] = True
    return out


def attach_agent_contract_fields(payload: dict) -> dict:
    if not isinstance(payload, dict) or not payload.get("state_type"):
        return payload
    try:
        from plugins.sts2.play_mode import agent_play_mode

        if not agent_play_mode():
            return payload
    except Exception:
        return payload
    out = dict(payload)
    out["agent_contract"] = format_agent_contract(out)
    try:
        from plugins.sts2.play_mode import autopilot_active

        out["autopilot_running"] = autopilot_active()
    except Exception:
        out["autopilot_running"] = False
    if agent_sole_decider():
        return sanitize_payload_for_agent(out)
    out["sole_decider"] = "llm_autopilot"
    return out
