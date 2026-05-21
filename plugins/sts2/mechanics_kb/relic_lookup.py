"""Lookup relic summaries from relics_index + combat relic modifiers."""

from __future__ import annotations

import re
from typing import Any

from plugins.sts2.mechanics_kb.store import (
    get_relic_entries,
    get_shop_relic_entries,
    relics_index_data,
)


def _norm_relic_id(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(raw).upper()).strip("_")


def lookup_relic(entry_id: str) -> dict[str, Any] | None:
    ent = (relics_index_data().get("entries") or {}).get(entry_id)
    if ent:
        return ent
    for row in get_relic_entries() + get_shop_relic_entries():
        if entry_id in (_norm_relic_id(x) for x in (row.get("match") or [row.get("id")])):
            return {
                "id": row.get("id"),
                "name": row.get("id"),
                "summary": str(row.get("effect", "")),
                "combat_modifier": True,
            }
    return None


def _player_relic_ids(state: dict) -> list[str]:
    player = state.get("player") or {}
    ids: list[str] = []
    for r in (player.get("relics") or []):
        if isinstance(r, dict):
            rid = r.get("id") or r.get("name") or ""
        else:
            rid = str(r)
        if rid:
            ids.append(_norm_relic_id(rid))
    return ids


def _shop_relic_ids(state: dict) -> list[str]:
    shop = state.get("shop") or {}
    ids: list[str] = []
    for r in (shop.get("relics") or []):
        if isinstance(r, dict):
            rid = r.get("id") or r.get("name") or ""
        else:
            rid = str(r)
        if rid:
            ids.append(_norm_relic_id(rid))
    return ids


def format_relic_context_brief(state: dict, *, max_items: int = 4) -> str:
    """Summaries for player/shop relics relevant to current screen."""
    st = str(state.get("state_type") or "")
    targets: list[str] = []
    if st in ("shop", "merchant", "fake_merchant"):
        targets = _shop_relic_ids(state)
    elif st in ("relic_select", "relic_select_boss", "treasure"):
        for r in (state.get("relic_select") or {}).get("relics") or []:
            if isinstance(r, dict):
                rid = r.get("id") or r.get("name")
                if rid:
                    targets.append(_norm_relic_id(str(rid)))
    else:
        targets = _player_relic_ids(state)

    if not targets:
        return ""
    lines = ["【遗物条目·wiki】"]
    shown = 0
    for rid in targets:
        ent = lookup_relic(rid)
        if not ent:
            continue
        summ = (ent.get("summary") or "")[:200]
        rar = ent.get("rarity") or ""
        tag = f"({rar}) " if rar else ""
        lines.append(f"  · {ent.get('name', rid)}: {tag}{summ}")
        shown += 1
        if shown >= max_items:
            break
    return "\n".join(lines) if shown else ""
