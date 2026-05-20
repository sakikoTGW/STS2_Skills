"""Resolve power stacks from MCP entity blobs using mechanics_kb match index."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from plugins.sts2.mechanics_kb.store import power_match_index


def _blob(power: dict) -> str:
    return " ".join(
        str(power.get(k) or "") for k in ("id", "name", "description", "type")
    )


def match_power_id(power: dict) -> Optional[str]:
    if not isinstance(power, dict):
        return None
    blob = _blob(power).lower()
    pid = str(power.get("id") or "").upper()
    if pid:
        for canon, patterns in power_match_index().items():
            if pid == canon or pid in [p.upper() for p in patterns]:
                return canon
    for canon, patterns in power_match_index().items():
        for pat in patterns:
            if pat.lower() in blob:
                return canon
    return None


def power_amount(power: dict, *, default: int = 1) -> int:
    for key in ("amount", "stacks", "count", "stack"):
        if power.get(key) is not None:
            try:
                return max(0, int(power[key]))
            except (TypeError, ValueError):
                pass
    return default


def collect_powers(entity: dict) -> Dict[str, int]:
    """Canonical power_id -> stacks (duration or intensity per KB entry)."""
    out: Dict[str, int] = {}
    if not isinstance(entity, dict):
        return out
    for p in entity.get("powers") or []:
        if not isinstance(p, dict):
            continue
        canon = match_power_id(p)
        if not canon:
            continue
        amt = power_amount(p)
        out[canon] = max(out.get(canon, 0), amt)
    for canon in power_match_index():
        for flat in (canon.lower(),):
            if entity.get(flat) is not None:
                try:
                    out[canon] = max(out.get(canon, 0), int(entity[flat]))
                except (TypeError, ValueError):
                    pass
    for stat, canon in (("strength", "STRENGTH"), ("dexterity", "DEXTERITY")):
        if entity.get(stat) is not None and canon not in out:
            try:
                out[canon] = int(entity[stat])
            except (TypeError, ValueError):
                pass
    return out


def has_duration_debuff(powers: Dict[str, int], debuff_id: str) -> bool:
    """Duration debuffs: active if stacks>0; stacks are turns not intensity."""
    return int(powers.get(debuff_id.upper(), 0) or 0) > 0


def relic_active(player: dict, relic_id: str) -> bool:
    from plugins.sts2.mechanics_kb.store import get_relic_entries

    for r in player.get("relics") or []:
        if not isinstance(r, dict):
            continue
        blob = " ".join(str(r.get(k) or "") for k in ("id", "name")).upper()
        ent = next((e for e in get_relic_entries() if e.get("id") == relic_id), None)
        if not ent:
            continue
        for m in ent.get("match") or []:
            if str(m).upper() in blob or str(m) in str(r.get("name") or ""):
                return True
    return False
