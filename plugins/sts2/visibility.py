"""Human-readable game snapshots for commentary, chat, and agent recall."""

from __future__ import annotations

from typing import Any

from plugins.sts2.safe_parse import normalize_options, option_label

_COMBAT = frozenset({"monster", "elite", "boss", "hand_select"})


def _card_label(card: dict) -> str:
    name = str(card.get("name") or card.get("id") or "?").strip()
    cost = card.get("cost", "?")
    idx = card.get("index", "?")
    playable = "✓" if card.get("can_play") else "×"
    return f"[{idx}]{name}({cost}){playable}"


def _run_line(state: dict) -> str:
    run = state.get("run") or {}
    parts = []
    ch = run.get("character") or run.get("character_id")
    if ch:
        parts.append(str(ch))
    floor = run.get("floor")
    if floor is not None:
        parts.append(f"第{floor}层")
    act = run.get("act")
    if act is not None:
        parts.append(f"幕{act}")
    gold = run.get("gold")
    if gold is not None:
        parts.append(f"金{gold}")
    asc = run.get("ascension")
    if asc is not None:
        parts.append(f"进阶{asc}")
    return " · ".join(parts) if parts else ""


def _player_line(state: dict) -> str:
    p = state.get("player") or {}
    hp = p.get("hp", p.get("current_hp", "?"))
    mx = p.get("max_hp", "?")
    blk = p.get("block", 0)
    en = p.get("energy", "?")
    return f"HP {hp}/{mx} | 格挡{blk} | 能量{en}"


def _hand_line(state: dict) -> str:
    hand = (state.get("player") or {}).get("hand") or []
    if not hand:
        return "手牌: (空)"
    return "手牌: " + ", ".join(_card_label(c) for c in hand)


def _enemies_line(state: dict) -> str:
    battle = state.get("battle") or {}
    enemies = battle.get("enemies") or []
    if not enemies:
        return ""
    bits = []
    for e in enemies:
        name = e.get("name") or e.get("id") or "敌人"
        hp = e.get("hp", "?")
        mx = e.get("max_hp", hp)
        intents = e.get("intents") or []
        intent_txt = ""
        if intents:
            it = intents[0]
            intent_txt = str(it.get("label") or it.get("type") or "")
        bits.append(f"{name} {hp}/{mx} 意图:{intent_txt or '?'}")
    rnd = battle.get("round")
    turn = battle.get("turn")
    head = f"战斗 回合{rnd or '?'} ({turn or '?'})"
    return head + " | " + "；".join(bits)


def _map_line(state: dict) -> str:
    m = state.get("map") or {}
    opts = m.get("next_options") or state.get("next_options") or []
    if not opts:
        return "地图: 等待选路或推进"
    parts = []
    for o in opts:
        t = o.get("type") or o.get("symbol") or "?"
        name = o.get("name") or o.get("id") or ""
        parts.append(f"#{o.get('index', '?')} {t} {name}".strip())
    return "地图可选: " + " | ".join(parts)


def _rewards_line(state: dict) -> str:
    rw = state.get("rewards") or {}
    items = [i for i in (rw.get("items") or []) if isinstance(i, dict)]
    if items:
        parts = []
        for o in items[:8]:
            t = o.get("type") or "?"
            name = o.get("name") or o.get("title") or ""
            claimed = o.get("claimed") or o.get("obtained")
            mark = "✓" if claimed else "○"
            parts.append(f"#{o.get('index', '?')} {t} {name} {mark}".strip())
        return "奖励: " + " | ".join(parts)
    opts = rw.get("options") or state.get("options") or []
    if not opts:
        return "奖励: 可 proceed"
    parts = []
    for o in opts[:8]:
        t = o.get("type") or o.get("reward_type") or "?"
        name = o.get("name") or o.get("title") or ""
        parts.append(f"#{o.get('index', '?')} {t} {name}".strip())
    return "奖励: " + " | ".join(parts)


def _event_line(state: dict) -> str:
    ev = state.get("event") or {}
    title = ev.get("event_name") or ev.get("event_id") or "事件"
    opts = ev.get("options") or []
    parts = [title]
    for o in opts[:6]:
        if o.get("is_locked"):
            continue
        parts.append(f"#{o.get('index', '?')} {o.get('title', '?')}")
    return "事件: " + " | ".join(parts)


def _menu_line(state: dict) -> str:
    screen = state.get("menu_screen") or "menu"
    opts = normalize_options(state.get("options") or [])
    names = []
    for o in opts[:12]:
        n = option_label(o)
        if n:
            names.append(n)
    return f"菜单({screen}): " + (", ".join(names) if names else "(无选项)")


def describe_situation(state: dict) -> str:
    """Multi-line snapshot of the current screen (for agent / user)."""
    if not state:
        return "(无状态)"
    st = str(state.get("state_type") or "unknown")
    lines: list[str] = []
    if st in _COMBAT:
        try:
            from plugins.sts2.combat_survival_gate import survival_alert_line

            alert = survival_alert_line(state) or str(state.get("survival_alert") or "")
            if alert:
                lines.append(alert)
        except Exception:
            alert = str(state.get("survival_alert") or "")
            if alert:
                lines.append(alert)
    lines.extend([f"【{st}】{_run_line(state)}", _player_line(state)])

    if st == "hand_select":
        hs = state.get("hand_select") or {}
        prompt = str(hs.get("prompt") or hs.get("mode") or "选牌")
        sel = hs.get("cards") or []
        parts = [
            f"[{c.get('index', '?')}]{c.get('name', '?')}"
            + ("+" if c.get("is_upgraded") else "")
            for c in sel[:10]
            if isinstance(c, dict)
        ]
        lines.append(f"选牌({prompt}): " + (", ".join(parts) or "(空)"))
        if hs.get("can_confirm"):
            lines.append("→ 可 combat_confirm_selection 确认")
        lines.append(_hand_line(state))
        el = _enemies_line(state)
        if el:
            lines.append(el)
    elif st in _COMBAT:
        lines.append(_hand_line(state))
        el = _enemies_line(state)
        if el:
            lines.append(el)
    elif st in ("treasure", "fake_merchant"):
        from plugins.sts2.treasure_rewards import format_treasure_offers

        lines.append(format_treasure_offers(state))
    elif st == "map":
        lines.append(_map_line(state))
    elif st == "rewards":
        lines.append(_rewards_line(state))
    elif st == "event":
        lines.append(_event_line(state))
    elif st == "menu":
        lines.append(_menu_line(state))
    elif st == "rest_site":
        rs = state.get("rest_site") or {}
        raw = rs.get("options") or state.get("options") or []
        opts = normalize_options(raw)
        if opts:
            lines.append(
                "营火: "
                + ", ".join(option_label(o) or "?" for o in opts[:8])
            )
        elif rs.get("can_proceed", True):
            lines.append("营火: (选项未列出) 用 proceed 离开")
        else:
            lines.append("营火: (无选项)")
    elif st == "shop":
        lines.append("商店界面 — 用 get_state 看商品列表")
    elif st == "crystal_sphere":
        from plugins.sts2.crystal_sphere import format_crystal_brief

        lines.append(format_crystal_brief(state))
    elif st == "card_reward":
        from plugins.sts2.reward_cards import format_card_offers, offer_reward_cards

        lines.append(format_card_offers(offer_reward_cards(state)))
    elif st == "card_select":
        from plugins.sts2.reward_cards import format_card_offers, offer_reward_cards

        lines.append(format_card_offers(offer_reward_cards(state)))
        cs = state.get("card_select") or {}
        if cs.get("preview_showing"):
            lines.append("(升级预览 — 确认或换选)")
    elif st in ("relic_select", "relic_select_boss"):
        relics = (state.get("relic_select") or {}).get("relics") or []
        if relics:
            parts = []
            for r in relics:
                parts.append(
                    f"#{r.get('index', '?')} {r.get('name') or r.get('id') or '?'}"
                )
            lines.append("遗物: " + " | ".join(parts))
        else:
            lines.append("遗物: (未解析到列表)")
    else:
        lines.append(_hand_line(state))

    return "\n".join(x for x in lines if x)


def describe_action(state: dict, body: dict) -> str:
    """Explain the planned or executed action in plain language."""
    action = str(body.get("action") or "")
    if not action:
        return "(无动作)"

    if action == "play_card":
        idx = body.get("card_index")
        target = body.get("target")
        card = _find_hand_card(state, idx)
        label = _card_label(card) if card else f"索引{idx}"
        if target:
            return f"出牌 → {label} → 目标 {target}"
        return f"出牌 → {label}"

    if action == "end_turn":
        return "结束回合"

    if action == "choose_map_node":
        return f"选路 → 节点 #{body.get('index', '?')}"

    if action == "menu_select":
        return f"菜单 → {body.get('option', '?')}"

    if action == "choose_event_option":
        ev = state.get("event") or {}
        opts = ev.get("options") or []
        ix = body.get("index")
        title = "?"
        for o in opts:
            if o.get("index") == ix:
                title = o.get("title", title)
                break
        return f"事件选项 → #{ix} {title}"

    if action == "claim_reward":
        return f"领取奖励 #{body.get('index', '?')}"

    if action == "claim_treasure_relic":
        return f"宝箱遗物 → #{body.get('index', '?')}"

    if action == "select_card_reward":
        from plugins.sts2.reward_cards import offer_reward_cards

        idx = body.get("card_index", body.get("index"))
        label = f"#{idx}"
        for c in offer_reward_cards(state):
            if c.get("index") == idx:
                label = f"#{idx} {c.get('name') or c.get('id') or '?'}"
                break
        return f"选牌奖励 → {label}"

    if action == "select_card":
        from plugins.sts2.reward_cards import offer_reward_cards

        idx = body.get("index", body.get("card_index"))
        label = f"#{idx}"
        for c in offer_reward_cards(state):
            if c.get("index") == idx:
                label = f"#{idx} {c.get('name') or c.get('id') or '?'}"
                break
        return f"选卡 → {label}"

    if action == "use_potion":
        return f"用药水 槽位{body.get('slot', '?')}"

    if action == "proceed":
        return "继续 / 推进"

    if action == "advance_dialogue":
        return "推进对话"

    if action == "crystal_sphere_click_cell":
        return f"水晶球占卜 → 格子 ({body.get('x', '?')}, {body.get('y', '?')})"

    if action == "crystal_sphere_set_tool":
        return f"水晶球工具 → {body.get('tool', '?')}"

    if action == "crystal_sphere_proceed":
        return "离开水晶球"

    return f"{action} {body}"


def _find_hand_card(state: dict, index: Any) -> dict | None:
    if index is None:
        return None
    try:
        want = int(index)
    except (TypeError, ValueError):
        return None
    for c in (state.get("player") or {}).get("hand") or []:
        if c.get("index") == want:
            return c
    return None


def format_turn_commentary(
    state: dict,
    body: dict,
    *,
    act_ok: bool = True,
    post_state: dict | None = None,
    err_msg: str = "",
) -> str:
    """Full turn line: situation + action + result (for live feed / chat)."""
    before = describe_situation(state)
    act = describe_action(state, body)
    status = "成功" if act_ok else f"失败{(': ' + err_msg) if err_msg else ''}"
    lines = [before, f"▶ {act} — {status}"]
    if post_state and post_state.get("state_type"):
        after = describe_situation(post_state)
        if after != before:
            lines.append("— 之后 —")
            lines.append(after)
    return "\n".join(lines)


def describe_delta(before: dict, after: dict) -> str:
    """Short diff when the player (or game) changed state between polls."""
    if not before or not after:
        return ""
    from plugins.sts2.action_trace import format_action_trace

    trace = format_action_trace(before, after)
    if trace:
        return trace
    lines: list[str] = []
    bst = before.get("state_type")
    ast = after.get("state_type")
    if bst != ast:
        lines.append(f"界面 {bst} → {ast}")

    br = before.get("run") or {}
    ar = after.get("run") or {}
    if br.get("floor") != ar.get("floor"):
        lines.append(f"层数 {br.get('floor')} → {ar.get('floor')}")

    bp = before.get("player") or {}
    ap = after.get("player") or {}
    if bp.get("hp") != ap.get("hp"):
        lines.append(f"生命 {bp.get('hp')} → {ap.get('hp')}")
    if bp.get("energy") != ap.get("energy"):
        lines.append(f"能量 {bp.get('energy')} → {ap.get('energy')}")
    if bp.get("block") != ap.get("block"):
        lines.append(f"格挡 {bp.get('block')} → {ap.get('block')}")

    bh = {(c.get("index"), c.get("id")) for c in (bp.get("hand") or [])}
    ah = {(c.get("index"), c.get("id")) for c in (ap.get("hand") or [])}
    if bh != ah:
        lines.append(f"手牌变化: {len(bh)}张 → {len(ah)}张")

    be = before.get("battle", {}).get("enemies") or []
    ae = after.get("battle", {}).get("enemies") or []
    if len(be) != len(ae) or any(
        e.get("hp") != ae[i].get("hp") for i, e in enumerate(be) if i < len(ae)
    ):
        lines.append("敌人状态更新")

    return "；".join(lines) if lines else ""


def state_fingerprint(state: dict) -> str:
    """Compact key for detecting user-driven changes between polls."""
    st = state.get("state_type")
    p = state.get("player") or {}
    hand_ids = tuple(
        (c.get("index"), c.get("id")) for c in (p.get("hand") or [])
    )
    run = state.get("run") or {}
    battle = state.get("battle") or {}
    foes = tuple(
        (e.get("entity_id"), e.get("hp")) for e in (battle.get("enemies") or [])
    )
    return f"{st}|f{run.get('floor')}|hp{p.get('hp')}|e{p.get('energy')}|h{hand_ids}|f{foes}"
