"""Minimal Hermes home helpers for the standalone hermes-sts2 package."""

from __future__ import annotations

import os
from pathlib import Path


def get_hermes_home() -> Path:
    val = os.environ.get("HERMES_HOME", "").strip()
    if val:
        return Path(val)
    return Path.home() / ".hermes"


def display_hermes_home() -> str:
    home = get_hermes_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)
