"""Load game_flow_kb JSON bundle."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def bundled_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "game_flow_kb"


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    fp = bundled_dir() / "catalog.json"
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("game_flow_kb catalog: %s", exc)
        return {}


@lru_cache(maxsize=1)
def _bundle() -> dict[str, Any]:
    root = bundled_dir()
    out: dict[str, Any] = {}
    for rel in load_catalog().get("entry_files") or []:
        data = _load(root / str(rel))
        if data:
            out[str(rel).replace(".json", "").split("/")[-1]] = data
    return out


def _load(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("game_flow_kb %s: %s", path, exc)
        return None


def ascension_data() -> dict[str, Any]:
    return dict(_bundle().get("ascension") or {})


def rest_data() -> dict[str, Any]:
    return dict(_bundle().get("rest_sites") or {})


def ancients_data() -> dict[str, Any]:
    return dict(_bundle().get("ancients") or {})


def map_data() -> dict[str, Any]:
    return dict(_bundle().get("map_flow") or {})


def screens_data() -> dict[str, Any]:
    return dict(_bundle().get("screens") or {})


def merchant_data() -> dict[str, Any]:
    return dict(_bundle().get("merchant") or {})


def elites_data() -> dict[str, Any]:
    return dict(_bundle().get("elites") or {})


def bosses_data() -> dict[str, Any]:
    return dict(_bundle().get("bosses") or {})


def events_data() -> dict[str, Any]:
    return dict(_bundle().get("events") or {})


def chests_data() -> dict[str, Any]:
    return dict(_bundle().get("chests") or {})


def potions_data() -> dict[str, Any]:
    return dict(_bundle().get("potions") or {})


def relic_catalog_data() -> dict[str, Any]:
    return dict(_bundle().get("relic_catalog") or {})


def neow_data() -> dict[str, Any]:
    return dict(_bundle().get("neow") or {})


def rewards_data() -> dict[str, Any]:
    return dict(_bundle().get("rewards") or {})


def events_catalog_data() -> dict[str, Any]:
    return dict(_bundle().get("events_catalog") or {})


def kb_version() -> int:
    return int(load_catalog().get("version") or 0)
