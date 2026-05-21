"""Screen-specific wiki KB briefs (boss/event/treasure/neow/potions/relics)."""

from __future__ import annotations

from plugins.sts2.game_flow_kb.store import (
    bosses_data,
    chests_data,
    elites_data,
    events_data,
    neow_data,
    potions_data,
    relic_catalog_data,
    rewards_data,
)


def format_boss_brief(state: dict) -> str:
    b = bosses_data()
    if not b:
        return ""
    run = state.get("run") or {}
    act = str(run.get("act") or "1")
    pool = (b.get("act_pools") or {}).get(act) or []
    lines = ["【Boss·wiki】"]
    if pool:
        lines.append(f"  幕{act}池: {', '.join(pool)}")
    rew = b.get("rewards") or {}
    g = rew.get("gold") or [100, 100]
    lines.append(f"  击败奖励: {g[0]}金 + 三选一稀有牌 + 可能药水")
    lines.append("  战前上一格必为营火；A10 第三幕连打两 Boss 中间无营火")
    for hint in (b.get("agent_hints") or [])[:2]:
        lines.append(f"  · {hint}")
    return "\n".join(lines)


def format_event_brief(state: dict) -> str:
    from plugins.sts2.game_flow_kb.event_lookup import format_event_detail_brief

    detail = format_event_detail_brief(state)
    if detail:
        return detail
    evd = events_data()
    if not evd:
        return ""
    lines = ["【事件·wiki】"]
    for hint in (evd.get("agent_hints") or [])[:4]:
        lines.append(f"  · {hint}")
    mp = evd.get("multiplayer_collaborative_events") or []
    if mp:
        lines.append(f"  联机协作事件例: {', '.join(mp[:4])}")
    return "\n".join(lines)


def format_neow_brief(state: dict) -> str:
    n = neow_data()
    if not n:
        return ""
    lines = ["【涅奥·wiki】"]
    for rule in (n.get("pick_rules") or [])[:2]:
        lines.append(f"  · {rule}")
    curse = n.get("curse_pool") or []
    pos = n.get("positive_pool") or []
    if curse:
        lines.append("  诅咒池例: " + ", ".join(c.get("id", "?") for c in curse[:4]))
    if pos:
        lines.append("  正面池例: " + ", ".join(c.get("id", "?") for c in pos[:4]))
    return "\n".join(lines)


def format_treasure_brief(state: dict) -> str:
    c = chests_data()
    if not c:
        return ""
    gr = c.get("gold_range") or [42, 53]
    lines = [
        "【宝箱·wiki】",
        f"  默认: 遗物 + {gr[0]}–{gr[1]}金 (A3 起 {c.get('gold_range_ascension_3', gr)})",
    ]
    if c.get("guaranteed_mid_act"):
        lines.append("  每幕中途必有一间宝箱房")
    return "\n".join(lines)


def format_potions_brief(state: dict) -> str:
    p = potions_data()
    if not p:
        return ""
    lines = [
        "【药水·wiki】",
        f"  默认{p.get('default_slots', 3)}槽(A4={p.get('ascension_4_slots', 2)})；用瓶不耗能量不算出牌",
    ]
    rw = p.get("rarity_weights") or {}
    if rw:
        lines.append(
            f"  稀有度: 普{rw.get('common', 0.65):.0%} 罕{rw.get('uncommon', 0.25):.0%} 稀{rw.get('rare', 0.1):.0%}"
        )
    return "\n".join(lines)


def format_relic_catalog_brief(state: dict) -> str:
    from plugins.sts2.mechanics_kb.relic_lookup import format_relic_context_brief

    ctx = format_relic_context_brief(state)
    r = relic_catalog_data()
    if not r and not ctx:
        return ""
    lines = []
    if ctx:
        lines.append(ctx)
    if r:
        run = state.get("run") or {}
        ch = str(run.get("character") or "").lower()
        starters = r.get("starter_relics") or {}
        rules = ["【遗物规则·wiki】"]
        if ch and ch in starters:
            s = starters[ch]
            rules.append(
                f"  本角色开局: {s.get('starter')} → 先古升级 {s.get('ancient_upgrade')}"
            )
        for hint in (r.get("agent_hints") or [])[:3]:
            rules.append(f"  · {hint}")
        lines.append("\n".join(rules))
    return "\n\n".join(lines)


def format_rewards_brief(state: dict) -> str:
    rw = rewards_data()
    if not rw:
        return ""
    lines = ["【奖励屏·wiki】"]
    for hint in (rw.get("agent_hints") or [])[:3]:
        lines.append(f"  · {hint}")
    return "\n".join(lines)


def format_elite_brief(state: dict) -> str:
    ed = elites_data()
    if not ed:
        return ""
    run = state.get("run") or {}
    act = str(run.get("act") or "1")
    pool = (ed.get("act_pools") or {}).get(act) or []
    lines = []
    if pool:
        lines.append(f"  本幕精英池: {', '.join(pool)}")
    rew = ed.get("rewards") or {}
    gr = rew.get("gold_range") or [35, 45]
    lines.append(f"  精英奖励: 遗物+{gr[0]}–{gr[1]}金+选牌")
    return "\n".join(lines) if lines else ""
