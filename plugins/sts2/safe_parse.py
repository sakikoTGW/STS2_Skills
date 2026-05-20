"""Normalize API option blobs (dict or str)."""

from __future__ import annotations

from typing import Any, Dict, List


def option_label(opt: Any) -> str:
    if isinstance(opt, str):
        return opt.strip()
    if isinstance(opt, dict):
        return str(opt.get("option") or opt.get("name") or opt.get("title") or "").strip()
    return str(opt).strip()


def option_enabled(opt: Any) -> bool:
    if isinstance(opt, dict):
        return opt.get("enabled", opt.get("is_enabled", True)) is not False
    return True


def normalize_options(raw: Any) -> List[Dict[str, Any]]:
    """Coerce mixed option lists to dicts with at least 'option' key."""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(raw):
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({"option": item, "index": i})
    return out
