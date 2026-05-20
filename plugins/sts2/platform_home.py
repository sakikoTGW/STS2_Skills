"""Resolve STS2 runtime data directory across Hermes, OpenClaw, and AstrBot."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_sts2_home(*, config_log_dir: str = "") -> Path:
    """Pick where logs, action_log, strategy, and caches live.

    Precedence:
    1. ``sts2.log_dir`` in host config (Hermes ``config.yaml``)
    2. ``STS2_HOME`` environment variable
    3. ``$OPENCLAW_HOME/sts2`` when ``OPENCLAW_HOME`` is set
    4. ``$ASTRBOT_DATA/sts2`` when ``ASTRBOT_DATA`` is set
    5. ``$HERMES_HOME/sts2`` (Hermes default)
    """
    raw = (config_log_dir or "").strip()
    if raw:
        return Path(raw).expanduser()

    env_home = (os.environ.get("STS2_HOME") or "").strip()
    if env_home:
        return Path(env_home).expanduser()

    oc = (os.environ.get("OPENCLAW_HOME") or "").strip()
    if oc:
        return Path(oc).expanduser() / "sts2"

    ab = (os.environ.get("ASTRBOT_DATA") or "").strip()
    if ab:
        return Path(ab).expanduser() / "sts2"

    from hermes_constants import get_hermes_home

    return get_hermes_home() / "sts2"
