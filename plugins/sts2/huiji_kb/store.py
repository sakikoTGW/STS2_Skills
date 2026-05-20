"""Load/save huiji KB — bundled references + user cache."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)

_SUFFIX_NUM = re.compile(r"_(\d+)$")


def bundled_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "huiji_kb"


def user_kb_path() -> Path:
    p = sts2_home() / "knowledge" / "huiji_kb"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _enemies_file(path: Path) -> Path:
    return path / "enemies.json"


@lru_cache(maxsize=1)
def _load_loop_overlays() -> Dict[str, Dict[str, Any]]:
    fp = bundled_dir() / "loops_act1.json"
    if not fp.is_file():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return dict(data.get("entries") or {})
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("loops_act1 load failed: %s", exc)
        return {}


@lru_cache(maxsize=1)
def _load_bundled() -> Dict[str, Any]:
    fp = _enemies_file(bundled_dir())
    if not fp.is_file():
        return {"version": 0, "entries": {}}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("bundled huiji_kb load failed: %s", exc)
        return {"version": 0, "entries": {}}
    entries = dict(data.get("entries") or {})
    for eid, loop in _load_loop_overlays().items():
        if eid in entries and not entries[eid].get("behavior_loop"):
            entries[eid]["behavior_loop"] = loop
        elif eid not in entries:
            entries[eid] = {"id": eid, "behavior_loop": loop, "source": "loops_act1"}
    data["entries"] = entries
    return data


def _load_user() -> Dict[str, Any]:
    fp = _enemies_file(user_kb_path())
    if not fp.is_file():
        return {"version": 0, "entries": {}}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("user huiji_kb load failed: %s", exc)
        return {"version": 0, "entries": {}}


def _merged_entries() -> Dict[str, Dict[str, Any]]:
    bundled = (_load_bundled().get("entries") or {}).copy()
    user = (_load_user().get("entries") or {})
    bundled.update(user)  # user overrides bundled
    return bundled


def _alias_index() -> Dict[str, str]:
    idx: Dict[str, str] = {}
    for eid, ent in _merged_entries().items():
        idx[_norm(eid)] = eid
        for key in ("name_zh", "name_en", "wiki_title"):
            v = str(ent.get(key) or "").strip()
            if v:
                idx[_norm(v)] = eid
        for alias in ent.get("aliases") or []:
            if alias:
                idx[_norm(str(alias))] = eid
        for name in ent.get("names") or []:
            if name:
                idx[_norm(str(name))] = eid
    return idx


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "").strip().upper())


def normalize_enemy_id(raw: str) -> str:
    key = _norm(raw)
    key = _SUFFIX_NUM.sub("", key)
    aliases = (_load_bundled().get("aliases") or {})
    if key in aliases:
        return str(aliases[key]).upper()
    idx = _alias_index()
    return idx.get(key, key)


def _resolve_inherits(ent: Dict[str, Any]) -> Dict[str, Any]:
    parent_id = str(ent.get("inherits") or "").strip().upper()
    if not parent_id:
        return _finalize_entry(ent)
    parent = _merged_entries().get(parent_id)
    if not parent:
        return _finalize_entry(ent)
    merged = dict(parent)
    merged.update(ent)
    return _finalize_entry(merged)


def _finalize_entry(ent: Dict[str, Any]) -> Dict[str, Any]:
    from plugins.sts2.huiji_kb.loops import attach_behavior_loop

    return attach_behavior_loop(dict(ent))


def lookup_enemy(item_id: str) -> Optional[Dict[str, Any]]:
    eid = normalize_enemy_id(item_id)
    ent = _merged_entries().get(eid)
    if ent:
        return _resolve_inherits(dict(ent))
    idx = _alias_index()
    alt = idx.get(_norm(item_id))
    if alt:
        ent = _merged_entries().get(alt)
        return _resolve_inherits(dict(ent)) if ent else None
    return None


def get_behavior_loop(item_id: str) -> Optional[Dict[str, Any]]:
    ent = lookup_enemy(item_id)
    if not ent:
        return None
    return ent.get("behavior_loop")


def get_enemy(item_id: str) -> Optional[Dict[str, Any]]:
    return lookup_enemy(item_id)


def list_enemies(*, act: Optional[int] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ent in _merged_entries().values():
        if act is not None:
            acts = ent.get("acts") or []
            if acts and act not in acts:
                continue
        out.append(dict(ent))
    return sorted(out, key=lambda e: str(e.get("id") or ""))


def import_enemy_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    eid = normalize_enemy_id(str(entry.get("id") or entry.get("wiki_title") or ""))
    if not eid or eid == "UNKNOWN":
        raise ValueError("entry missing id")
    entry = dict(entry)
    entry["id"] = eid
    entry["synced_at"] = datetime.now(timezone.utc).isoformat()

    data = _load_user()
    entries = dict(data.get("entries") or {})
    merged = dict(entries.get(eid) or {})
    merged.update(entry)
    entries[eid] = merged
    data["entries"] = entries
    data["version"] = int(data.get("version") or 0) + 1
    data["updated_at"] = entry["synced_at"]
    fp = _enemies_file(user_kb_path())
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _load_bundled.cache_clear()
    return merged


def save_user_store(entries: Dict[str, Dict[str, Any]], *, source: str = "sync") -> Path:
    fp = _enemies_file(user_kb_path())
    payload = {
        "version": 1,
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _load_bundled.cache_clear()
    return fp


def kb_stats() -> Dict[str, Any]:
    bundled = len((_load_bundled().get("entries") or {}))
    user = len((_load_user().get("entries") or {}))
    merged = len(_merged_entries())
    return {
        "bundled": bundled,
        "user": user,
        "merged": merged,
        "bundled_path": str(_enemies_file(bundled_dir())),
        "user_path": str(_enemies_file(user_kb_path())),
    }


def to_knowledge_entry(huiji: Dict[str, Any]) -> Dict[str, Any]:
    """Shape for plugins.sts2.knowledge yaml store."""
    intents = huiji.get("intents") or []
    intent_txt = "; ".join(
        f"{i.get('name','?')}({i.get('type','?')}"
        + (f" {i.get('damage')}伤" if i.get("damage") else "")
        + ")"
        for i in intents[:8]
    )
    snippet_parts = [
        str(huiji.get("name_zh") or huiji.get("wiki_title") or ""),
        f"HP:{huiji.get('hp_solo') or huiji.get('hp') or '?'}",
    ]
    if intent_txt:
        snippet_parts.append(f"意图:{intent_txt}")
    if huiji.get("pattern"):
        snippet_parts.append(str(huiji["pattern"]))
    if huiji.get("combat_plan"):
        snippet_parts.append(str(huiji["combat_plan"]))
    rule = str(huiji.get("rule") or huiji.get("combat_plan") or "")[:200]
    tags = list(huiji.get("tags") or [])
    tier = str(huiji.get("tier") or "")
    if tier == "elite":
        tags.append("elite")
    return {
        "id": normalize_enemy_id(str(huiji.get("id") or "")),
        "name": str(huiji.get("name_zh") or huiji.get("wiki_title") or huiji.get("id")),
        "tags": tags,
        "reward_bonus": 0.0,
        "combat_bonus": 12.0 if tier == "elite" else 6.0,
        "rule": rule,
        "wiki_snippet": " | ".join(snippet_parts)[:500],
        "source": huiji.get("source") or "huiji_kb",
        "huiji": True,
        "intents": intents,
        "hp_solo": huiji.get("hp_solo"),
        "pattern": huiji.get("pattern"),
        "combat_plan": huiji.get("combat_plan"),
    }
