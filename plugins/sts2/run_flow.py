"""Deterministic menu / game_over → new run (no LLM)."""

from __future__ import annotations

from typing import Any, Dict, Optional


def next_menu_action(state: dict) -> Optional[Dict[str, Any]]:
    """One menu/game_over action toward starting a standard Ironclad run."""
    st = str(state.get("state_type") or "")
    screen = str(state.get("menu_screen") or "").lower()
    from plugins.sts2.safe_parse import normalize_options, option_enabled, option_label

    opts = normalize_options(state.get("options") or [])

    def _names() -> list[str]:
        out = []
        for o in opts:
            if not option_enabled(o):
                continue
            n = option_label(o)
            if n:
                out.append(n)
        return out

    names = [x.lower() for x in _names()]

    if st == "game_over":
        for key in ("continue", "confirm", "proceed", "main_menu", "menu"):
            if key in names:
                return {"action": "menu_select", "option": key}
        # API often exposes no options on defeat — main_menu is required
        return {"action": "menu_select", "option": "main_menu"}

    if st != "menu":
        return None

    if screen in ("tutorial_prompt", "popup", "ftue"):
        for key in ("ignore", "close", "no", "continue"):
            if key in names:
                return {"action": "menu_select", "option": key}

    # Intro / credits timeline — must advance, not back
    if screen in ("timeline", "intro", "credits", "cutscene"):
        for key in ("advance", "continue", "skip", "proceed"):
            if key in names:
                return {"action": "menu_select", "option": key}
        if "back" in names and len(names) == 1:
            return {"action": "menu_select", "option": "back"}

    for key in ("continue", "embark", "confirm"):
        if key in names:
            return {"action": "menu_select", "option": key}

    if "singleplayer" in names:
        return {"action": "menu_select", "option": "singleplayer"}
    if "standard" in names:
        return {"action": "menu_select", "option": "standard"}

    for o in opts:
        if isinstance(o, dict) and o.get("is_locked"):
            continue
        opt = option_label(o)
        low = opt.lower()
        if "ironclad" in low or opt.upper() == "IRONCLAD":
            return {"action": "menu_select", "option": opt}

    if "embark" in names:
        return {"action": "menu_select", "option": "embark"}
    if "confirm" in names:
        return {"action": "menu_select", "option": "confirm"}

    if names:
        return {"action": "menu_select", "option": _names()[0]}
    return {"action": "proceed"}


def in_run(state: dict) -> bool:
    return str(state.get("state_type") or "") in (
        "monster",
        "elite",
        "boss",
        "map",
        "event",
        "rewards",
        "card_reward",
        "rest_site",
        "shop",
        "treasure",
        "hand_select",
        "card_select",
    )


def menu_fingerprint(state: dict) -> str:
    """Stable key for detecting menu soft-lock."""
    screen = str(state.get("menu_screen") or "")
    from plugins.sts2.safe_parse import normalize_options, option_enabled, option_label

    opts = normalize_options(state.get("options") or [])
    names = sorted(
        option_label(o).lower()
        for o in opts
        if option_enabled(o) and option_label(o)
    )
    return f"{state.get('state_type')}|{screen}|{','.join(names)}"


def menu_is_opening_sequence(state: dict, *, was_in_run: bool) -> bool:
    """Title intro / FTUE — not a finished run."""
    if str(state.get("state_type") or "") != "menu":
        return False
    if was_in_run:
        return False
    screen = str(state.get("menu_screen") or "").lower()
    if screen in ("timeline", "intro", "credits", "cutscene", "tutorial_prompt", "popup", "ftue"):
        return True
    run = state.get("run") or {}
    try:
        floor = int(run.get("floor") or 0)
    except (TypeError, ValueError):
        floor = 0
    return floor <= 0 and screen in ("", "main", "title")


def run_needs_restart(state: dict, *, was_in_run: bool) -> bool:
    """True when we should treat the screen as post-death / post-run, not title intro."""
    st = str(state.get("state_type") or "")
    if st == "game_over":
        return True
    if st != "menu":
        return False
    if not was_in_run:
        return False
    return not menu_is_opening_sequence(state, was_in_run=was_in_run)
