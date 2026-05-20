"""Preferred playable character for menu / new-run automation."""

from __future__ import annotations

import os
from typing import Any

# Canonical IDs (STS2 / MCP menu labels are usually English names)
VALID_CHARACTERS = ("IRONCLAD", "SILENT", "DEFECT", "NECROBINDER", "REGENT")
DEFAULT_CHARACTER = "IRONCLAD"
ALL_CHARACTERS = VALID_CHARACTERS

_ALIASES: dict[str, str] = {
    "ironclad": "IRONCLAD",
    "iron_clad": "IRONCLAD",
    "战士": "IRONCLAD",
    "铁甲": "IRONCLAD",
    "铁甲战士": "IRONCLAD",
    "silent": "SILENT",
    "the silent": "SILENT",
    "猎手": "SILENT",
    "刺客": "SILENT",
    "defect": "DEFECT",
    "机器人": "DEFECT",
    "necrobinder": "NECROBINDER",
    "necrobancer": "NECROBINDER",
    "necro_binder": "NECROBINDER",
    "死灵": "NECROBINDER",
    "亡灵": "NECROBINDER",
    "regent": "REGENT",
    "储君": "REGENT",
    "皇子": "REGENT",
}

# Legacy typo used in older decision.py preference lists
_LEGACY_ALIASES = {"necrobancer": "NECROBINDER"}


def normalize_character(name: str | None) -> str | None:
    """Map user/config input to a canonical character id, or None if unknown."""
    if not name:
        return None
    raw = str(name).strip()
    if not raw:
        return None
    key = raw.lower().replace("-", "_").replace(" ", "_")
    if key in _ALIASES:
        return _ALIASES[key]
    upper = raw.upper().replace("-", "_").replace(" ", "_")
    if upper in VALID_CHARACTERS:
        return upper
    if upper in _LEGACY_ALIASES:
        return _LEGACY_ALIASES[upper]
    # Substring match for menu labels like "Ironclad (Unlocked)"
    low = raw.lower()
    for alias, canon in _ALIASES.items():
        if len(alias) >= 4 and alias in low:
            return canon
    for canon in VALID_CHARACTERS:
        if canon.lower() in low:
            return canon
    return None


def get_preferred_character(cfg: dict[str, Any] | None = None) -> str:
    """Preferred character from env ``STS2_CHARACTER``, then config, else Ironclad."""
    env = (os.environ.get("STS2_CHARACTER") or "").strip()
    if env:
        norm = normalize_character(env)
        if norm:
            return norm
    if cfg:
        norm = normalize_character(str(cfg.get("character") or ""))
        if norm:
            return norm
    return DEFAULT_CHARACTER


def preference_order(cfg: dict[str, Any] | None = None) -> tuple[str, ...]:
    """Character ids to try on character-select menus (preferred first)."""
    pref = get_preferred_character(cfg)
    rest = [c for c in ALL_CHARACTERS if c != pref]
    return (pref, *rest)


def _option_label(opt: dict) -> str:
    return str(opt.get("option") or opt.get("title") or opt.get("name") or "")


def option_matches_character(opt: dict, role: str) -> bool:
    """True if menu option corresponds to ``role`` (canonical id)."""
    label = _option_label(opt)
    if not label:
        return False
    upper = label.upper()
    role_u = role.upper()
    if role_u in upper or upper == role_u:
        return True
    low = label.lower()
    canon = normalize_character(role) or role_u
    for alias, mapped in _ALIASES.items():
        if mapped == canon and len(alias) >= 3 and alias in low:
            return True
    norm = normalize_character(label)
    return norm == canon


def pick_character_menu_action(
    opts: list,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Pick unlocked character matching config preference."""
    if cfg is None:
        try:
            from plugins.sts2.config import load_sts2_config

            cfg = load_sts2_config()
        except Exception:
            cfg = {}
    for role in preference_order(cfg):
        for o in opts:
            if not isinstance(o, dict) or o.get("is_locked"):
                continue
            if option_matches_character(o, role):
                opt = _option_label(o) or role
                return {"action": "menu_select", "option": opt}
    for o in opts:
        if isinstance(o, dict) and not o.get("is_locked"):
            opt = _option_label(o)
            if opt:
                return {"action": "menu_select", "option": opt}
    return None


def find_character_in_options(opts: list, *, cfg: dict[str, Any] | None = None) -> str | None:
    """Return the menu option label for the preferred character if present."""
    if cfg is None:
        try:
            from plugins.sts2.config import load_sts2_config

            cfg = load_sts2_config()
        except Exception:
            cfg = {}
    pref = get_preferred_character(cfg)
    from plugins.sts2.safe_parse import option_enabled, option_label

    for o in opts:
        if not option_enabled(o):
            continue
        if isinstance(o, dict) and o.get("is_locked"):
            continue
        if option_matches_character(o if isinstance(o, dict) else {"option": option_label(o)}, pref):
            return option_label(o) if not isinstance(o, dict) else (_option_label(o) or pref)
    return None
