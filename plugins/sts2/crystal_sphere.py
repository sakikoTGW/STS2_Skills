"""Crystal Sphere minigame — STS2MCP actions and agent-facing aliases."""

from __future__ import annotations

import json

CLICK_ACTION = "crystal_sphere_click_cell"
SET_TOOL_ACTION = "crystal_sphere_set_tool"
PROCEED_ACTION = "crystal_sphere_proceed"

_CLICK_ALIASES = frozenset(
    {
        "crystal_sphere_click_cell",
        "click_cell",
        "click",
        "divine",
        "crystal_sphere_divine",
        "crystal_sphere_select",
        "choose_cell",
        "select",
    }
)
_TOOL_ALIASES = frozenset(
    {
        "crystal_sphere_set_tool",
        "set_tool",
        "switch_tool",
    }
)
_TOOL_NAMES = frozenset({"big", "small", "large", "minor"})


def _cs_block(state: dict) -> dict:
    raw = state.get("crystal_sphere")
    return raw if isinstance(raw, dict) else {}


def divinations_remaining(state: dict) -> int:
    cs = _cs_block(state)
    for key in (
        "divinations_remaining",
        "remaining_divinations",
        "charges_remaining",
        "divinations_left",
    ):
        if key in cs:
            try:
                return max(0, int(cs[key]))
            except (TypeError, ValueError):
                pass
        if key in state:
            try:
                return max(0, int(state[key]))
            except (TypeError, ValueError):
                pass
    return 0


def can_proceed(state: dict) -> bool:
    """Honor game flag; do not assume 0 charges ⇒ can leave."""
    cs = _cs_block(state)
    if cs.get("can_proceed") is True or state.get("can_proceed") is True:
        return True
    if cs.get("can_proceed") is False or state.get("can_proceed") is False:
        return False
    return divinations_remaining(state) <= 0


def map_next_options(state: dict) -> list[dict]:
    m = state.get("map") if isinstance(state.get("map"), dict) else {}
    opts = m.get("next_options") or state.get("next_options") or []
    return [o for o in opts if isinstance(o, dict)]


def crystal_sphere_stuck(state: dict) -> bool:
    """Charges spent but game still blocks proceed (e.g. bad cell revealed)."""
    if str(state.get("state_type") or "") != "crystal_sphere":
        return False
    return divinations_remaining(state) <= 0 and not can_proceed(state)


def crystal_sphere_stale_map(state: dict) -> bool:
    """API still says crystal_sphere while map routing data is present."""
    if str(state.get("state_type") or "") != "crystal_sphere":
        return False
    return bool(map_next_options(state))


def effective_screen(state: dict) -> str:
    """Best guess of what the player actually sees."""
    st = str(state.get("state_type") or "")
    if st == "crystal_sphere" and crystal_sphere_stale_map(state):
        return "map"
    return st


def current_tool(state: dict) -> str:
    cs = _cs_block(state)
    tool = str(cs.get("tool") or state.get("tool") or "big").strip().lower()
    if tool in ("large", "major"):
        return "big"
    if tool in ("minor", "little"):
        return "small"
    return tool if tool in ("big", "small") else "big"


def clickable_cells(state: dict) -> list[dict]:
    cs = _cs_block(state)
    cells = cs.get("clickable_cells") or cs.get("cells") or state.get("clickable_cells")
    if not isinstance(cells, list):
        return []
    return [c for c in cells if isinstance(c, dict)]


def pick_click_xy(state: dict) -> tuple[int, int]:
    cells = clickable_cells(state)
    highlighted = [c for c in cells if c.get("is_highlighted")]
    pool = highlighted or cells
    if not pool:
        return 3, 1

    def _xy(c: dict) -> tuple[int, int]:
        try:
            return int(c.get("x", 0)), int(c.get("y", 0))
        except (TypeError, ValueError):
            return 0, 0

    xs = [_xy(c)[0] for c in pool]
    ys = [_xy(c)[1] for c in pool]
    return round(sum(xs) / len(xs)), round(sum(ys) / len(ys))


def _parse_xy(body: dict) -> tuple[int, int] | None:
    for xk, yk in (("x", "y"), ("cell_x", "cell_y"), ("col", "row")):
        if xk in body and yk in body:
            try:
                return int(body[xk]), int(body[yk])
            except (TypeError, ValueError):
                return None
    return None


def normalize_crystal_action(state: dict, body: dict) -> dict:
    """Map agent guesses to STS2MCP crystal_sphere_* actions."""
    action = str(body.get("action") or "").strip().lower()
    if not action:
        return decide_crystal_sphere(state)

    if action == "choose_map_node":
        opts = map_next_options(state)
        if opts:
            try:
                ix = int(body.get("index", -1))
            except (TypeError, ValueError):
                ix = -1
            if not any(o.get("index") == ix for o in opts):
                ix = int(opts[0].get("index", 0))
            return {"action": "choose_map_node", "index": ix}

    if action in ("proceed_to_map",):
        return {"action": PROCEED_ACTION}

    stuck = crystal_sphere_stuck(state)
    stale_map = crystal_sphere_stale_map(state)

    if action in _TOOL_NAMES and _parse_xy(body) is None:
        return {"action": SET_TOOL_ACTION, "tool": "big" if action in ("big", "large") else "small"}

    if action in _TOOL_ALIASES or action == SET_TOOL_ACTION:
        tool = str(body.get("tool") or current_tool(state)).lower()
        if tool in ("large", "major"):
            tool = "big"
        elif tool in ("minor", "little"):
            tool = "small"
        if tool not in ("big", "small"):
            tool = current_tool(state)
        return {"action": SET_TOOL_ACTION, "tool": tool}

    if action in _CLICK_ALIASES or action == CLICK_ACTION:
        if stuck or stale_map:
            return _recovery_action(state)
        xy = _parse_xy(body)
        if xy is None:
            xy = pick_click_xy(state)
        return {"action": CLICK_ACTION, "x": xy[0], "y": xy[1]}

    if action in ("proceed", PROCEED_ACTION, "leave", "exit", "skip", "continue"):
        if can_proceed(state):
            return {"action": PROCEED_ACTION}
        if divinations_remaining(state) > 0:
            xy = pick_click_xy(state)
            return {"action": CLICK_ACTION, "x": xy[0], "y": xy[1]}
        return _recovery_action(state)

    # Illegal combat/menu actions on this screen
    if action in (
        "play_card",
        "end_turn",
        "menu_select",
        "choose_event_option",
    ):
        return decide_crystal_sphere(state)

    return body


def _recovery_action(state: dict) -> dict:
    """Stuck or stale: try leave; if map data exists, route on map."""
    opts = map_next_options(state)
    if opts:
        return {"action": "choose_map_node", "index": int(opts[0].get("index", 0))}
    return {"action": PROCEED_ACTION}


def decide_crystal_sphere(state: dict) -> dict:
    """Rule fallback: use remaining divinations, then proceed."""
    if crystal_sphere_stale_map(state):
        return _recovery_action(state)
    if crystal_sphere_stuck(state):
        return _recovery_action(state)
    if can_proceed(state) and divinations_remaining(state) <= 0:
        return {"action": PROCEED_ACTION}
    if divinations_remaining(state) > 0:
        x, y = pick_click_xy(state)
        return {"action": CLICK_ACTION, "x": x, "y": y}
    if can_proceed(state):
        return {"action": PROCEED_ACTION}
    return _recovery_action(state)


def annotate_state(state: dict) -> dict:
    """Add desync hints for agents (API state_type vs visible screen)."""
    if not isinstance(state, dict):
        return state
    out = dict(state)
    eff = effective_screen(state)
    if eff != str(state.get("state_type") or ""):
        out["effective_screen"] = eff
    if crystal_sphere_stale_map(state):
        out["crystal_sphere_desync"] = "map_options_present"
    if crystal_sphere_stuck(state):
        out["crystal_sphere_stuck"] = True
    return out


def format_crystal_brief(state: dict) -> str:
    rem = divinations_remaining(state)
    tool = current_tool(state)
    cells = clickable_cells(state)
    hi = [c for c in cells if c.get("is_highlighted")]
    stuck = crystal_sphere_stuck(state)
    stale = crystal_sphere_stale_map(state)
    lines = [
        "【水晶球】必须用 STS2MCP 专用动作，勿用 proceed/divine/big 当 action。",
        f"当前工具={tool}（big=3×3 大刮，small=1×1 小刮）| 剩余占卜次数≈{rem}",
        "crystal_sphere_set_tool(tool=\"big\"|\"small\") → "
        "crystal_sphere_click_cell(x,y) → 次数用尽后 crystal_sphere_proceed()",
    ]
    if stale:
        from plugins.sts2.visibility import _map_line

        lines.append(
            "【状态不同步】state_type 仍是 crystal_sphere，但已有地图节点数据——"
            "若你肉眼已在地图，直接 choose_map_node(index)，勿再刮格。"
        )
        lines.append(_map_line(state))
    if stuck and not stale:
        lines.append(
            "【卡住】占卜次数已 0 且 can_proceed=false（常因点到坏格）。"
            "禁止继续 click_cell；试 crystal_sphere_proceed。"
            "若教练/你说已在地图，仍用 choose_map_node。"
        )
    if hi:
        sample = ", ".join(f"({c.get('x')},{c.get('y')})" for c in hi[:8])
        lines.append(f"推荐点击高亮格: {sample}")
    elif cells:
        sample = ", ".join(f"({c.get('x')},{c.get('y')})" for c in cells[:6])
        lines.append(f"可点格: {sample}")
    if rem > 0:
        x, y = pick_click_xy(state)
        lines.append(
            f"→ 示例: sts2_act {{\"action\":\"{CLICK_ACTION}\",\"x\":{x},\"y\":{y}}}"
        )
    elif can_proceed(state):
        lines.append(f'→ 占卜已用完: sts2_act {{"action":"{PROCEED_ACTION}"}}')
    elif stuck or stale:
        rec = _recovery_action(state)
        lines.append(f"→ 恢复: sts2_act {json.dumps(rec, ensure_ascii=False)}")
    else:
        lines.append("→ 继续 click_cell 直到 can_proceed 为 true。")
    return "\n".join(lines)
