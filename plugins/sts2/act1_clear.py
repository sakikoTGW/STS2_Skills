"""Run strategy — map/combat tuned per act (Act1–3 全剧)."""

from __future__ import annotations

_WIN_RULES: list[str] = [
    "通关优先：HP<50% 绝不选精英；地图有营火且HP<75% 必选营火。",
    "Act1 前9层只打普通战或?，HP>70% 才考虑精英。",
    "多怪战集火最低血敌人；预估伤害≥当前HP 必须先格挡再输出。",
    "奖励领完 proceed；阵亡后菜单自动开标准铁甲新局。",
]


def bootstrap_win_focus_rules() -> None:
    from plugins.sts2.notes import merge_strategy_rules

    merge_strategy_rules(_WIN_RULES, source="bootstrap")


def hp_ratio(state: dict | None) -> float:
    if not state:
        return 1.0
    player = state.get("player") or {}
    try:
        hp = int(player.get("hp", player.get("current_hp", 1)))
        max_hp = int(player.get("max_hp", hp) or hp or 1)
    except (TypeError, ValueError):
        return 1.0
    return hp / max_hp if max_hp > 0 else 1.0


def run_floor(state: dict | None) -> int:
    if not state:
        return 0
    run = state.get("run") or {}
    try:
        return int(run.get("floor") or run.get("floor_reached") or 0)
    except (TypeError, ValueError):
        return 0


def _option_label(option: dict) -> str:
    return " ".join(
        str(option.get(k) or "")
        for k in ("type", "symbol", "label", "room_type", "icon", "name", "title")
    ).lower()


def _run_act(state: dict | None) -> int:
    try:
        from plugins.sts2.run_victory import run_act

        return run_act(state)
    except Exception:
        return 1


def map_node_score(option: dict, state: dict | None) -> int:
    """Lower is better (same as min() pick)."""
    label = _option_label(option)
    ratio = hp_ratio(state)
    floor = run_floor(state)
    act = _run_act(state)
    elite_floor_min = {1: 12, 2: 12, 3: 14}.get(act, 12)
    elite_hp_min = {1: 0.62, 2: 0.58, 3: 0.62}.get(act, 0.55)
    cautious = False
    try:
        from plugins.sts2.lessons import should_avoid_elite_early

        cautious = should_avoid_elite_early()
    except Exception:
        pass

    if "boss" in label:
        return 3

    # Act1 末段：少绕路，直奔 Boss（HP 尚可时）
    if act == 1 and floor >= 46:
        if "rest" in label or "campfire" in label:
            return -18 if ratio < 0.72 else 4
        if "monster" in label or "combat" in label or "m" == label.strip():
            return 5 if ratio >= 0.5 else 12
        if "event" in label or "?" in label:
            return 22

    if "elite" in label:
        if ratio < 0.5:
            return 99
        if act == 1 and floor < 12 and ratio < 0.72:
            return 92
        if ratio < elite_hp_min or floor < elite_floor_min:
            return 90
        if act == 1 and floor < 14 and ratio < 0.72:
            return 85
        if act == 1 and floor <= 9 and ratio < 0.78:
            return 88
        if cautious or ratio < 0.68:
            return 50
        if ratio < 0.72:
            return 45
        return 14 if act >= 2 else 18

    if "rest" in label or "campfire" in label:
        if ratio < 0.75:
            return -15
        if ratio < 0.55:
            return -25
        return 2

    if "shop" in label or "merchant" in label:
        return 6 if ratio < 0.45 else 8

    if "event" in label or "?" in label or "unknown" in label:
        if ratio < 0.4:
            return 4
        return 7

    if "monster" in label or "combat" in label or "m" == label.strip():
        if cautious and floor < 10:
            return 5
        return 8

    return 10


def pick_map_node(opts: list, state: dict | None) -> dict:
    if not opts:
        return {"action": "proceed"}
    best = min(opts, key=lambda o: map_node_score(o, state))
    return {"action": "choose_map_node", "index": best.get("index", 0)}


def combat_danger_multiplier(state: dict) -> float:
    """Scale block priority in elite/boss or when about to die."""
    mult = 1.0
    st = str((state or {}).get("state_type") or "").lower()
    if st in ("elite", "boss"):
        mult += 0.35
    ratio = hp_ratio(state)
    if ratio < 0.35:
        mult += 0.5
    elif ratio < 0.55:
        mult += 0.25
    return mult
