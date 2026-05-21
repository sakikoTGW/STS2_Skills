"""Load ``sts2`` settings without the full Hermes CLI (standalone pip / GitHub repo)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def _config_candidates() -> list[Path]:
    explicit = (os.environ.get("STS2_CONFIG_PATH") or "").strip()
    if explicit:
        return [Path(explicit).expanduser()]
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path.expanduser()).lower()
        if key not in seen:
            seen.add(key)
            candidates.append(path.expanduser())

    home = Path.home()
    add(home / ".config" / "sts2" / "config.yaml")
    try:
        from plugins.sts2.platform_home import (
            default_sts2_config_path,
            resolve_astrbot_data_dir,
            resolve_openclaw_home,
        )

        add(default_sts2_config_path("standalone"))
        add(resolve_openclaw_home() / "sts2" / "config.yaml")
        add(resolve_astrbot_data_dir() / "sts2" / "config.yaml")
    except Exception:
        pass
    add(home / ".hermes" / "config.yaml")
    try:
        from hermes_constants import get_hermes_home

        add(get_hermes_home() / "sts2" / "config.yaml")
    except Exception:
        pass
    return candidates


def load_sts2_section() -> dict[str, Any]:
    """Return the ``sts2:`` block from the first readable config file."""
    for path in _config_candidates():
        if not path.is_file():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(raw, dict):
            continue
        section = raw.get("sts2")
        if isinstance(section, dict):
            return dict(section)
    return {}
