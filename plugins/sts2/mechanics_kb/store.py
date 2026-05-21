"""Load bundled mechanics KB + optional user overrides."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)


def bundled_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "mechanics_kb"


def user_dir() -> Path:
    p = sts2_home() / "knowledge" / "mechanics_kb"
    p.mkdir(parents=True, exist_ok=True)
    return p


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    fp = bundled_dir() / "catalog.json"
    if not fp.is_file():
        return {"version": 0, "entry_files": []}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("mechanics_kb catalog load failed: %s", exc)
        return {"version": 0, "entry_files": []}


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("mechanics_kb load %s failed: %s", path, exc)
        return None


@lru_cache(maxsize=1)
def _merged_bundle() -> dict[str, Any]:
    cat = load_catalog()
    root = bundled_dir()
    out: dict[str, Any] = {
        "catalog": cat,
        "powers": {},
        "power_match": {},
        "relics": [],
        "shop_relics": [],
        "special_multipliers": [],
        "card_debuffs": {},
        "core_cards": {},
        "multi_hit": {},
        "pipeline": {},
        "wiki_examples": [],
    }
    for rel in cat.get("entry_files") or []:
        rel_s = str(rel)
        data = _load_json(root / rel_s)
        if not data:
            continue
        if rel_s.endswith("damage_pipeline.json"):
            out["pipeline"] = data
            out["wiki_examples"].extend(data.get("wiki_examples") or [])
        elif "powers/" in rel_s:
            for ent in data.get("entries") or []:
                if isinstance(ent, dict) and ent.get("id"):
                    out["powers"][str(ent["id"])] = ent
            out["power_match"].update(data.get("power_match") or {})
        elif "modifiers/relics" in rel_s:
            out["relics"].extend(data.get("entries") or [])
        elif "modifiers/shop" in rel_s:
            out["shop_relics"] = data.get("entries") or []
        elif "modifiers/special" in rel_s:
            out["special_multipliers"].extend(data.get("entries") or [])
        elif "cards/debuff" in rel_s:
            out["card_debuffs"] = data.get("cards") or {}
        elif "cards/core" in rel_s:
            out["core_cards"] = data.get("cards") or {}
        elif "cards/multi_hit" in rel_s:
            out["multi_hit"] = data
        elif "relics_index" in rel_s:
            out["relics_index"] = data
    user_ov = _load_json(user_dir() / "overrides.json")
    if isinstance(user_ov, dict):
        for ent in user_ov.get("power_overrides") or []:
            if isinstance(ent, dict) and ent.get("id"):
                out["powers"][str(ent["id"])] = {
                    **out["powers"].get(str(ent["id"]), {}),
                    **ent,
                }
    return out


def power_match_index() -> dict[str, str]:
    return dict(_merged_bundle().get("power_match") or {})


def get_power_entry(power_id: str) -> dict[str, Any] | None:
    return (_merged_bundle().get("powers") or {}).get(power_id.upper())


def get_pipeline() -> dict[str, Any]:
    return dict(_merged_bundle().get("pipeline") or {})


def lookup_wiki_examples() -> list[dict[str, Any]]:
    return list(_merged_bundle().get("wiki_examples") or [])


def get_card_debuff_table() -> dict[str, Any]:
    return dict(_merged_bundle().get("card_debuffs") or {})


def get_multi_hit_table() -> dict[str, Any]:
    return dict((_merged_bundle().get("multi_hit") or {}).get("cards") or {})


def get_multi_hit_patterns() -> list[dict[str, Any]]:
    return list((_merged_bundle().get("multi_hit") or {}).get("parse_patterns") or [])


def get_relic_entries() -> list[dict[str, Any]]:
    return list(_merged_bundle().get("relics") or [])


def get_shop_relic_entries() -> list[dict[str, Any]]:
    return list(_merged_bundle().get("shop_relics") or [])


def get_core_card_table() -> dict[str, Any]:
    return dict(_merged_bundle().get("core_cards") or {})


def relics_index_data() -> dict[str, Any]:
    raw = _merged_bundle().get("relics_index")
    if isinstance(raw, dict) and raw.get("entries"):
        return raw
    return {"entries": raw if isinstance(raw, dict) else {}}


def get_special_multipliers() -> list[dict[str, Any]]:
    return list(_merged_bundle().get("special_multipliers") or [])


def kb_version() -> int:
    return int(load_catalog().get("version") or 0)
