"""Ascension modifiers + heal math (ancient vs rest)."""

from __future__ import annotations

import math
from typing import Any

from plugins.sts2.game_flow_kb.store import ancients_data, ascension_data, rest_data
from plugins.sts2.mechanics_kb.power_parse import relic_active


def _ascension_level(state: dict) -> int:
    run = state.get("run") or {}
    try:
        return max(0, int(run.get("ascension") or run.get("ascension_level") or 0))
    except (TypeError, ValueError):
        return 0


def _player_hp(state: dict) -> tuple[int, int]:
    p = state.get("player") or {}
    try:
        hp = int(p.get("hp", p.get("current_hp", 0)))
        mx = int(p.get("max_hp", hp) or 1)
        return hp, max(1, mx)
    except (TypeError, ValueError):
        return 0, 1


def active_ascension_modifiers(state: dict) -> list[dict[str, Any]]:
    """Cumulative modifiers for current run ascension level."""
    lvl = _ascension_level(state)
    levels = (ascension_data().get("levels") or {})
    out: list[dict[str, Any]] = []
    for i in range(1, lvl + 1):
        ent = levels.get(str(i)) or levels.get(i)
        if ent:
            out.append({"level": i, **ent})
    return out


def format_ascension_block(state: dict) -> str:
    lvl = _ascension_level(state)
    if lvl <= 0:
        return "【进阶】当前 0 进阶（标准难度）"
    lines = [f"【进阶 v{lvl}·累加生效】"]
    for m in active_ascension_modifiers(state):
        lines.append(f"  A{m['level']} {m.get('name_zh') or m.get('name')}: {m.get('effect')}")
    if lvl >= 2:
        lines.append("  ⚠ A2 疲惫旅人：先古/涅奥类回血=缺失HP×80%，营火30%不受影响")
    if lvl >= 10:
        lines.append("  ⚠ A10：第三幕双 Boss")
    return "\n".join(lines)


def rest_heal_amount(state: dict) -> dict[str, Any]:
    """Predict Rest option heal (not ancient)."""
    hp, mx = _player_hp(state)
    player = state.get("player") or {}
    std = (rest_data().get("standard_options") or {}).get("rest") or {}
    ratio = float(std.get("heal_ratio_max_hp") or 0.3)
    heal = int(math.floor(mx * ratio))
    max_hp_gain = 0
    for rid, ent in (rest_data().get("relic_modifiers") or {}).items():
        if relic_active(player, rid):
            heal += int(ent.get("heal_flat") or 0)
            max_hp_gain += int(ent.get("max_hp_on_rest") or 0)
    after = min(mx, hp + heal)
    return {
        "heal": heal,
        "hp_before": hp,
        "max_hp": mx,
        "hp_after": after,
        "max_hp_gain": max_hp_gain,
        "missing": mx - hp,
    }


def ancient_heal_amount(state: dict, *, missing_hp: int | None = None) -> dict[str, Any]:
    """Ascension-aware heal when ancient/Neow restores missing HP."""
    hp, mx = _player_hp(state)
    missing = missing_hp if missing_hp is not None else max(0, mx - hp)
    rules = (ancients_data().get("heal_rules") or {})
    ratio = float(rules.get("default_missing_hp_heal_ratio") or 1.0)
    lvl = _ascension_level(state)
    if lvl >= 2:
        ratio = float(rules.get("ascension_2_missing_hp_heal_ratio") or 0.8)
    heal = int(math.floor(missing * ratio))
    return {
        "heal": heal,
        "missing": missing,
        "ratio": ratio,
        "hp_after": min(mx, hp + heal),
        "ascension_note": "A2 疲惫旅人" if lvl >= 2 else "",
    }
