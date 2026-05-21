"""Lookup per-event wiki catalog for event screen."""

from __future__ import annotations

import re
from typing import Any

from plugins.sts2.game_flow_kb.store import events_catalog_data


def _norm_event_id(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")


def resolve_event_id(state: dict) -> str | None:
    ev = state.get("event") or {}
    for key in ("event_id", "id", "event_name", "name"):
        val = ev.get(key)
        if val:
            return _norm_event_id(str(val))
    return None


def lookup_event(entry_id: str) -> dict[str, Any] | None:
    return (events_catalog_data().get("entries") or {}).get(entry_id)


def format_event_detail_brief(state: dict) -> str:
    """Per-event options from events_catalog (if crawled)."""
    eid = resolve_event_id(state)
    if not eid:
        return ""
    ent = lookup_event(eid)
    if not ent:
        # fuzzy: match by name substring
        entries = events_catalog_data().get("entries") or {}
        ev = state.get("event") or {}
        name = str(ev.get("event_name") or ev.get("name") or "").lower()
        for k, v in entries.items():
            if name and name in str(v.get("name", "")).lower():
                ent = v
                eid = k
                break
    if not ent:
        return ""
    lines = [f"【事件·{ent.get('name', eid)}】"]
    if ent.get("act_region"):
        lines.append(f"  区域: {ent['act_region']}")
    if ent.get("summary"):
        lines.append(f"  {ent['summary'][:320]}")
    for opt in (ent.get("options") or [])[:6]:
        label = opt.get("label") or "?"
        outs = opt.get("outcomes") or []
        if outs:
            lines.append(f"  · [{label}] " + " | ".join(outs[:4]))
        elif opt.get("raw"):
            lines.append(f"  · [{label}] {opt['raw'][:120]}")
    return "\n".join(lines)
