"""Run-level combat objective — win the act/run, minimize HP loss; not single-turn greed."""

from __future__ import annotations


def run_objective_lines(state: dict) -> list[str]:
    """Context-aware run goals (floor/act/hp) for brief + LLM."""
    run = state.get("run") or {}
    p = state.get("player") or {}
    try:
        floor = int(run.get("floor") or 0)
        act = int(run.get("act") or 1)
        hp = int(p.get("hp", p.get("current_hp", 0)))
        mx = int(p.get("max_hp", hp) or hp or 1)
    except (TypeError, ValueError):
        floor, act, hp, mx = 0, 1, 0, 1
    hp_pct = int(100 * hp / mx) if mx else 0

    lines = [
        "【整局目标·优先于单回合贪心】",
        "第一目的：通关本局（活到 Boss 并打赢），不是本回合伤害数字最大。",
        "第二目的：降低战损——少掉血比快打完更重要；多留 HP 给精英/Boss/营火价值。",
        "已知怪物有机制与意图循环 → 按 T+0/T+1/T+2 规划，做**局内最优线**，勿只做单回合最优。",
    ]
    if hp_pct < 45:
        lines.append(
            f"  当前 HP {hp}/{mx}({hp_pct}%)：倾向保守——多防、少赌、药水留给必死线；"
            "能稳杀再输出，勿为省 1 回合多挨一刀。"
        )
    elif hp_pct >= 75 and floor <= 6:
        lines.append(
            f"  当前 HP 较满、第{floor}层：可适度贪输出，但仍按循环留牌/留费给下回合高伤回合。"
        )
    if act >= 2 and floor >= 40:
        lines.append("  深幕/高层：每点 HP 都贵；无必要不交换血量换速度。")
    return lines


def format_run_objective_block(state: dict) -> str:
    """Inject at top of combat coaching."""
    extra = _planning_questions()
    return "\n".join(run_objective_lines(state) + [""] + extra)


def _planning_questions() -> list[str]:
    return [
        "【局内规划·出牌前自问】",
        "1) 这场战斗还要几回合？按意图循环，下 2～3 回合哪回合必须格挡/哪回合可输出？",
        "2) 本牌是服务「整战少掉血」还是只为本回合好看？（易伤/虚弱别打在即将休息的怪上）",
        "3) 留能量/留牌给下回合高伤，是否比本回合多打 6 点更值得？",
        "4) 能稳斩杀且战损可接受才集火；否则均匀压血/先解威胁，避免触发蟹怒等机制暴毙。",
        "5) 打完这场后还要走多少节点？药水/血量是否留给下一精英？",
    ]


def llm_run_objective_system() -> str:
    """Paragraph for combat_play_brain system prompt."""
    return (
        "【决策层级】整局通关 > 本场战损最小 > 当前回合效率。"
        "怪物机制与意图循环已知时，用多回合计划（T+0～T+2）选局内最优线，禁止单回合贪心："
        "勿为本回合多伤而浪费下回合格挡费；勿把 debuff 打在即将休息的怪上；"
        "斩杀仅当「稳杀且总战损更低」；快打只在不额外掉血时成立。"
        "commentary 须写清：本战预计还有几回合、按循环本步在计划中的位置、对通关/战损的影响。"
    )


def fsm_memory_run_hint() -> str:
    return (
        "[整局目标] 以通关与控战损为先，按怪物意图循环做局内多回合最优，非单回合最优。"
    )


def _hp_ratio(state: dict) -> float:
    p = state.get("player") or {}
    try:
        hp = int(p.get("hp", p.get("current_hp", 1)))
        mx = int(p.get("max_hp", hp) or hp or 1)
        return hp / mx if mx > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def map_route_objective_lines(state: dict) -> list[str]:
    """Map screen: path choice serves run clear + HP budget, not greed."""
    run = state.get("run") or {}
    try:
        floor = int(run.get("floor") or 0)
        act = int(run.get("act") or 1)
    except (TypeError, ValueError):
        floor, act = 0, 1
    hp_pct = int(100 * _hp_ratio(state))

    lines = [
        "【路线·整局目标】",
        "选路第一目的：提高**通关概率**（活到 Boss 并打赢），不是本幕多拿遗物/多打精英。",
        "第二目的：**控战损**——路线是 HP 预算分配：精英/事件是花血换强度，营火/绕路是回血止损。",
        "禁止泛攻略式「前期必多精英」；用本账号统计 + 已采纳规则 + 当前 HP/牌/遗物判断。",
    ]
    if hp_pct < 50:
        lines.append(
            f"  HP≈{hp_pct}%：优先营火/弱怪/安全事件，慎连精英；Boss 前尽量回到可扛 2 回合高伤的血线。"
        )
    elif hp_pct >= 70 and act == 1 and floor <= 12:
        lines.append(
            f"  HP≈{hp_pct}% Act{act} 前段：可评估 1 次精英换遗物，但若统计里精英后阵亡多 → 改绕路。"
        )
    if act >= 2:
        lines.append("  深幕：每点 HP 更贵；精英收益须覆盖「战后掉血 + 下段路径风险」。")
    return lines


def map_route_planning_questions(state: dict, options: list[dict]) -> list[str]:
    """Multi-step path thinking before choose_map_node."""
    run = state.get("run") or {}
    try:
        floor = int(run.get("floor") or 0)
    except (TypeError, ValueError):
        floor = 0
    lines = [
        "【路线·局内规划·选 index 前自问】",
        "1) 到 Boss 还要几步？这条分支总 HP 成本是否可接受（精英+事件+缺营火）？",
        "2) 下一场若是精英，战后 HP 够撑后续路径吗？不够 → 营火/弱怪/商店（买药水）优先。",
        "3) ? 事件：可能省血也可能暴血 —— 低血时权重低于营火。",
        "4) 本局 build 缺什么？缺防/缺伤/缺回复 → 用路线补，勿为遗物连赌精英。",
        f"5) 当前第{floor}层：Boss/营火/商店在图上相对位置 —— 勿为近路精英透支远路营火。",
    ]
    if options:
        kinds = []
        for o in options[:6]:
            label = " ".join(
                str(o.get(k) or "")
                for k in ("type", "symbol", "name", "label")
            ).lower()
            if "elite" in label:
                kinds.append("精英")
            elif "rest" in label:
                kinds.append("营火")
            elif "?" in label or "event" in label:
                kinds.append("?")
            elif "shop" in label:
                kinds.append("商店")
            else:
                kinds.append("战/其他")
        if kinds:
            lines.append(f"  眼前分支类型: {', '.join(kinds)} —— 对照上面 5 问选 index。")
    return lines


def format_map_run_objective_block(state: dict, options: list[dict] | None = None) -> str:
    opts = options or []
    return "\n".join(
        map_route_objective_lines(state)
        + [""]
        + map_route_planning_questions(state, opts)
    )


def llm_map_route_system() -> str:
    return (
        "【路线决策层级】通关整局 > 本幕战损可控 > 单点贪（连精英、贪?）。"
        "规则必须「候选：当 Act/层/HP/build…则选 elite|rest|monster|event」且基于本账号数据。"
        "禁止无上下文的固定血线%；禁止「铁甲 Act1 必多精英」类泛攻略。"
    )
