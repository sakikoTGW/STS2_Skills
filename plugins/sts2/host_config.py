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
    home = Path.home()
    return [
        home / ".config" / "sts2" / "config.yaml",
        home / ".hermes" / "config.yaml",
    ]


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
