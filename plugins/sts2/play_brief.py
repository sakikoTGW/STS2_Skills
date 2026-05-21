"""Inject structured play guidance into sts2_get_state / sts2_act (agent-facing)."""

from __future__ import annotations

from plugins.sts2.visibility import describe_situation

_COMBAT = frozenset({"monster", "elite", "boss", "hand_select"})


def build_play_brief(state: dict) -> str:
    """Agent decision context — assembled by decision_context (L0→L4)."""
    from plugins.sts2.decision_context import assemble_play_brief

    base = assemble_play_brief(state)
    if not state:
        return base

    st = str(state.get("state_type") or "")
    head = describe_situation(state)
    extras: list[str] = []

    contract = str(state.get("manual_contract") or "").strip()
    if contract:
        extras.append(contract)

    legal = state.get("legal_actions")
    if isinstance(legal, list) and legal:
        lines_la = ["【可执行动作·照抄 sts2_act】"]
        for a in legal[:14]:
            if a.get("allowed"):
                lines_la.append("  " + str(a.get("label") or a))
        extras.append("\n".join(lines_la))

    if st in _COMBAT:
        alert = str(state.get("survival_alert") or "").strip()
        if not alert:
            try:
                from plugins.sts2.combat_survival_gate import survival_alert_line

                alert = survival_alert_line(state)
            except Exception:
                alert = ""
        if alert and alert not in head and alert not in base:
            extras.append(alert)

    extras.append(head)
    if extras:
        return base + "\n\n" + "\n\n".join(extras)
    return base


def build_screen_brief(state: dict) -> str:
    """L2 screen body — map / combat detail / rewards (no macro/discipline)."""
    if not state:
        return ""
    st = str(state.get("state_type") or "")
    parts: list[str] = []

    if st in _COMBAT:
        parts.append(_combat_block(state))
        if st == "hand_select":
            try:
                from plugins.sts2.upgrade_advisor import (
                    collect_upgrade_candidates,
                    format_upgrade_brief,
                    is_upgrade_screen,
                )

                if is_upgrade_screen(state):
                    parts.append(
                        format_upgrade_brief(
                            state,
                            collect_upgrade_candidates(state),
                            context="战斗内武装",
                        )
                    )
            except Exception:
                pass
    elif st == "event":
        parts.append(_event_block(state))
    elif st == "map":
        parts.append(_map_block(state))
    elif st in ("card_reward", "card_select"):
        parts.append(_card_pick_block(state))
    elif st in ("treasure", "fake_merchant") or (
        st == "relic_select" and (state.get("treasure") or state.get("treasure_room"))
    ):
        parts.append(_treasure_block(state))
    elif st == "rewards":
        from plugins.sts2.rewards_screen import format_rewards_brief

        parts.append(format_rewards_brief(state))
    elif st == "rest_site":
        try:
            from plugins.sts2.upgrade_advisor import format_rest_site_brief

            parts.append(format_rest_site_brief(state))
        except Exception:
            parts.append(
                "【营火】choose_rest_option(index)；options 为空且 can_proceed 才 proceed。"
            )
    elif st == "bundle_select":
        parts.append(
            "【卷轴箱】select_bundle(index) → confirm_bundle_selection；勿盲 proceed。"
        )
    elif st == "menu":
        parts.append("【菜单】menu_select(option) 用选项原文，勿 proceed。")
    elif st == "crystal_sphere":
        from plugins.sts2.crystal_sphere import format_crystal_brief

        parts.append(format_crystal_brief(state))

    return "\n\n".join(p for p in parts if p)


def discipline_block(state: dict) -> str:
    st = str(state.get("state_type") or "")
    return _discipline_block(st)


def _discipline_block(st: str) -> str:
    if st == "hand_select":
        return "【纪律】武装/选牌：升级屏看【敲牌·升级决策】→ select/confirm；勿当弃牌屏。"
    if st in _COMBAT:
        return (
            "【纪律】决策顺序：整局目标(通关+控战损) → 五区状态机 → 局内多回合计划(T+0~2) "
            "→ 伤害账本 → 手牌战术；think_required 时读 combat_think。"
            "同一玩家回合内：有能量且手牌可出 → 连打多张牌（尤其格挡叠满），用尽再 end_turn。"
            "工具循环：每次 sts2_act 只发一个动作 → get_state 看新 index/能量 → 可再 act；"
            "勿把「一次 act」误当成「整回合只出一张牌」。"
        )
    if st == "event":
        return "【纪律】事件屏禁止 menu_select；用 advance_dialogue / choose_event_option。"
    if st == "crystal_sphere":
        return (
            "【纪律】水晶球：有占卜次数才 click_cell；次数用尽用 crystal_sphere_proceed。"
            "教练说已在地图或 state 含 next_options → choose_map_node，勿再刮格。"
        )
    if st == "map":
        return (
            "【纪律】地图：先读【路线·整局目标】与五问，再 choose_map_node；"
            "选路服务通关+控战损，勿连赌精英。每次 get_state 再看统计。"
        )
    if st in ("rest_site", "card_select"):
        return (
            "【纪律】敲牌：读【敲牌·升级决策】排序与「敲后收益」；"
            "已+勿敲；低血营火先 heal；smith 仅当有≥55分敲目标。"
        )
    if st == "rewards":
        return (
            "【纪律】战后奖励屏：逐项 claim_reward；有未领禁止 proceed。"
            "金币通常先领；卡牌会进 select_card_reward 再选。"
        )
    return "【纪律】每次 sts2_act 前 sts2_get_state(summary=true)；勿猜 index。"


def _combat_block(state: dict) -> str:
    from plugins.sts2.combat_brief import format_combat_brief

    return format_combat_brief(state)


def _treasure_block(state: dict) -> str:
    from plugins.sts2.treasure_rewards import (
        TREASURE_CLAIM_ACTION,
        format_treasure_offers,
        treasure_claimables,
    )

    items = treasure_claimables(state)
    unclaimed = [
        it
        for it in items
        if not it.get("claimed") and not it.get("obtained") and not it.get("picked")
    ]
    lines = [
        "【宝箱】先拿遗物，禁止对宝箱用 claim_reward（那是战后奖励屏）。",
        format_treasure_offers(state),
    ]
    if unclaimed:
        for it in unclaimed[:6]:
            ix = it.get("index", 0)
            name = it.get("name") or it.get("id") or "?"
            lines.append(
                f"  → sts2_act {{\"action\":\"{TREASURE_CLAIM_ACTION}\",\"index\":{ix}}}  ({name})"
            )
        lines.append("拿完所有未领取项后再 proceed / proceed_to_map 离开。")
    else:
        tr = state.get("treasure") or {}
        if tr.get("can_proceed", True):
            lines.append("→ 已无未领遗物: sts2_act {\"action\":\"proceed\"}")
        else:
            lines.append("→ 尝试 menu_select 打开宝箱或 claim_treasure_relic index=0")
    return "\n".join(lines)


def _event_block(state: dict) -> str:
    ev = state.get("event") or {}
    opts = [o for o in (ev.get("options") or []) if isinstance(o, dict)]
    pickable = [o for o in opts if not o.get("is_locked")]
    lines = [f"事件: {ev.get('event_name') or ev.get('event_id') or '?'}"]
    name_l = str(ev.get("event_name") or ev.get("event_id") or "").lower()
    if any(x in name_l for x in ("neow", "涅奥", "ancient", "先古", "orobas", "pael", "tezc")):
        try:
            from plugins.sts2.game_flow_kb.ascension import (
                ancient_heal_amount,
                format_ascension_block,
            )

            lines.append("【先古】三选一必选；不可跳过")
            lines.append(format_ascension_block(state))
            ah = ancient_heal_amount(state)
            if ah["missing"] > 0:
                lines.append(
                    f"若奖励为补缺失生命: +{ah['heal']}HP (缺失×{ah['ratio']:.0%})"
                )
        except Exception:
            pass
    if ev.get("in_dialogue"):
        lines.append("→ 对话中: sts2_act {\"action\":\"advance_dialogue\"}")
    for o in pickable[:8]:
        ix = o.get("index", "?")
        title = o.get("title") or "?"
        lock = " (锁定)" if o.get("is_locked") else ""
        lines.append(
            f"  choose_event_option index={ix}  「{title}」{lock}"
        )
    if not pickable and not ev.get("in_dialogue"):
        lines.append("→ 无选项时可 proceed")
    return "\n".join(lines)


def _map_block(state: dict) -> str:
    try:
        from plugins.sts2.map_route_learn import format_map_route_brief

        block = format_map_route_brief(state)
        try:
            from plugins.sts2.run_act_planner import format_map_operational_brief

            op = format_map_operational_brief(state)
            block = (block + "\n\n" + op) if block and op else (block or op)
        except Exception:
            pass
        if block:
            return block
    except Exception:
        pass
    m = state.get("map") or {}
    opts = m.get("next_options") or state.get("next_options") or []
    lines = ["【地图】choose_map_node(index)："]
    for o in opts[:8]:
        if isinstance(o, dict):
            lines.append(
                f"  index={o.get('index')} type={o.get('type', o.get('symbol', '?'))} "
                f"{o.get('name') or o.get('id') or ''}"
            )
    return "\n".join(lines) if len(lines) > 1 else "【地图】等待选路。"


def _card_pick_block(state: dict) -> str:
    from plugins.sts2.reward_cards import offer_reward_cards

    st = str(state.get("state_type") or "")
    cards = offer_reward_cards(state)
    try:
        from plugins.sts2.run_objective import format_run_objective_block

        run_goal = format_run_objective_block(state) + "\n\n"
    except Exception:
        run_goal = ""
    try:
        from plugins.sts2.build_knowledge import format_build_pick_brief

        build_block = format_build_pick_brief(state, cards)
    except Exception:
        build_block = ""
    cs = state.get("card_select") or {}

    if st == "card_select":
        prefix = "\n\n".join(x for x in (run_goal, build_block) if x)
        try:
            from plugins.sts2.upgrade_advisor import (
                collect_upgrade_candidates,
                format_upgrade_brief,
                is_upgrade_screen,
            )

            if is_upgrade_screen(state):
                up_cards = collect_upgrade_candidates(state)
                prefix = (
                    "\n\n".join(
                        x
                        for x in (
                            prefix,
                            format_upgrade_brief(state, up_cards, context="营火/敲牌"),
                        )
                        if x
                    )
                    + "\n\n"
                )
        except Exception:
            pass
        lines = [
            "【移牌/升级/变换屏】不是战后选卡奖励！",
            "  点选: sts2_act {\"action\":\"select_card\",\"index\":N}",
            "  多选: 重复 select_card 切换勾选",
            "  确认: sts2_act {\"action\":\"confirm_selection\"}",
            "  取消: {\"action\":\"cancel_selection\"}",
            "  禁止: menu_select / choose_event_option / select_card_reward",
        ]
        if cs.get("preview_showing"):
            lines.append("  (当前为升级预览 → confirm_selection 或 cancel_selection)")
        if cs.get("can_confirm"):
            lines.append("  → 已可 confirm_selection")
        lines.append("可选牌:")
        for c in cards[:8]:
            if isinstance(c, dict):
                sel = "✓" if c.get("selected") or c.get("is_selected") else "○"
                lines.append(
                    f"  {sel} index={c.get('index')} {c.get('name') or c.get('id')}"
                )
        body = "\n".join(lines)
        return f"{prefix}\n\n{body}" if prefix else body

    prefix = "\n\n".join(x for x in (run_goal, build_block) if x)
    lines = ["【战后选卡】select_card_reward(card_index) 或 skip/proceed："]
    for c in cards[:6]:
        if isinstance(c, dict):
            lines.append(
                f"  card_index={c.get('index')} {c.get('name') or c.get('id')}"
            )
    body = "\n".join(lines)
    return f"{prefix}\n\n{body}" if prefix else body
