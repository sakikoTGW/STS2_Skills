"""Preferred playable character for menu / new-run automation."""

from __future__ import annotations

import os
from typing import Any

# Canonical IDs (STS2 / MCP menu labels are usually English names)
VALID_CHARACTERS = ("IRONCLAD", "SILENT", "DEFECT", "NECROBINDER", "REGENT")
DEFAULT_CHARACTER = "IRONCLAD"
DEFAULT_CHARACTER_INDEX = 0
ALL_CHARACTERS = VALID_CHARACTERS

# Config file uses 0–4; env/CLI may still use index, English id, or Chinese name.
CHARACTER_BY_INDEX: dict[int, str] = {
    0: "IRONCLAD",
    1: "SILENT",
    2: "DEFECT",
    3: "NECROBINDER",
    4: "REGENT",
}
INDEX_BY_CHARACTER: dict[str, int] = {v: k for k, v in CHARACTER_BY_INDEX.items()}

# Display names (简体中文)
CHARACTER_ZH: dict[str, str] = {
    "IRONCLAD": "铁甲战士",
    "SILENT": "静默猎手",
    "DEFECT": "故障机器人",
    "NECROBINDER": "亡灵契约师",
    "REGENT": "储君",
}

_ALIASES: dict[str, str] = {
    "ironclad": "IRONCLAD",
    "iron_clad": "IRONCLAD",
    "铁甲战士": "IRONCLAD",
    "铁甲": "IRONCLAD",
    "silent": "SILENT",
    "the silent": "SILENT",
    "静默猎手": "SILENT",
    "猎手": "SILENT",
    "刺客": "SILENT",
    "defect": "DEFECT",
    "故障机器人": "DEFECT",
    "机器人": "DEFECT",
    "necrobinder": "NECROBINDER",
    "necrobancer": "NECROBINDER",
    "necro_binder": "NECROBINDER",
    "亡灵契约师": "NECROBINDER",
    "死灵": "NECROBINDER",
    "亡灵": "NECROBINDER",
    "regent": "REGENT",
    "储君": "REGENT",
}

_LEGACY_ALIASES = {"necrobancer": "NECROBINDER"}


def _canonical_from_text(raw: str) -> str | None:
    """Map free-form text to a canonical id (no index / recursion)."""
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
    low = raw.lower()
    for alias, canon in _ALIASES.items():
        if len(alias) >= 4 and alias in low:
            return canon
    for canon in VALID_CHARACTERS:
        if canon.lower() in low:
            return canon
    return None


def character_index(value: str | int | None) -> int | None:
    """Parse config value to index 0–4, or None if unknown."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value in CHARACTER_BY_INDEX else None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        idx = int(raw)
        return idx if idx in CHARACTER_BY_INDEX else None
    canon = _canonical_from_text(raw)
    if canon:
        return INDEX_BY_CHARACTER.get(canon)
    return None


def normalize_character(name: str | int | None) -> str | None:
    """Map user/config input to a canonical character id, or None if unknown."""
    idx = character_index(name)
    if idx is not None:
        return CHARACTER_BY_INDEX[idx]
    return None


def resolve_character_setting(value: str | int | None) -> tuple[int, str]:
    """Return (index 0–4, canonical id). Unknown → default ironclad."""
    idx = character_index(value)
    if idx is not None:
        return idx, CHARACTER_BY_INDEX[idx]
    return DEFAULT_CHARACTER_INDEX, DEFAULT_CHARACTER


def character_label_zh(canon: str) -> str:
    return CHARACTER_ZH.get(canon.upper(), canon)


def get_preferred_character(cfg: dict[str, Any] | None = None) -> str:
    """Preferred character id from env ``STS2_CHARACTER``, then config."""
    env = (os.environ.get("STS2_CHARACTER") or "").strip()
    if env:
        norm = normalize_character(env)
        if norm:
            return norm
    if cfg:
        _, canon = resolve_character_setting(cfg.get("character"))
        return canon
    return DEFAULT_CHARACTER


def get_preferred_character_index(cfg: dict[str, Any] | None = None) -> int:
    canon = get_preferred_character(cfg)
    return INDEX_BY_CHARACTER.get(canon, DEFAULT_CHARACTER_INDEX)


def preference_order(cfg: dict[str, Any] | None = None) -> tuple[str, ...]:
    pref = get_preferred_character(cfg)
    rest = [c for c in ALL_CHARACTERS if c != pref]
    return (pref, *rest)


def _option_label(opt: dict) -> str:
    return str(opt.get("option") or opt.get("title") or opt.get("name") or "")


def option_matches_character(opt: dict, role: str) -> bool:
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
        if option_matches_character(
            o if isinstance(o, dict) else {"option": option_label(o)}, pref
        ):
            return option_label(o) if not isinstance(o, dict) else (_option_label(o) or pref)
    return None
