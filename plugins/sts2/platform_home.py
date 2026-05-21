"""Resolve STS2 runtime data directory across Hermes, OpenClaw, AstrBot, and standalone."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_openclaw_home(explicit: str = "") -> Path:
    raw = (explicit or os.environ.get("OPENCLAW_HOME") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".openclaw"


def resolve_astrbot_data_dir(explicit: str = "") -> Path:
    from plugins.sts2.paths import resolve_astrbot_data_dir as _resolve

    return _resolve(explicit)


def _sts2_subdir(base: Path) -> Path:
    return base if base.name == "sts2" else base / "sts2"


def detect_runtime_host() -> str:
    """Best-effort active host: astrbot | openclaw | hermes | standalone."""
    if (os.environ.get("ASTRBOT_DATA") or "").strip():
        return "astrbot"
    if (os.environ.get("OPENCLAW_HOME") or "").strip():
        return "openclaw"
    for key in ("HERMES_TUI_STS2_BRIDGE", "HERMES_STS2_AGENT_PLAY", "HERMES_STS2_MOUNT_MODE"):
        if os.environ.get(key, "").strip().lower() in ("1", "true", "yes"):
            return "hermes"
    try:
        from hermes_cli.config import load_config

        if isinstance(load_config().get("sts2"), dict):
            return "hermes"
    except Exception:
        pass
    cfg = Path.home() / ".config" / "sts2" / "config.yaml"
    if cfg.is_file():
        return "standalone"
    return "standalone"


def default_sts2_config_path(host: str = "") -> Path:
    host = host or detect_runtime_host()
    if host == "openclaw":
        return _sts2_subdir(resolve_openclaw_home()) / "config.yaml"
    if host == "astrbot":
        return _sts2_subdir(resolve_astrbot_data_dir()) / "config.yaml"
    if host == "hermes":
        try:
            from hermes_constants import get_hermes_home

            return get_hermes_home() / "sts2" / "config.yaml"
        except Exception:
            pass
    return Path.home() / ".config" / "sts2" / "config.yaml"


def resolve_sts2_home(*, config_log_dir: str = "") -> Path:
    """Runtime data: logs, strategy, trajectories, game_dir.txt.

    Precedence:
    1. ``sts2.log_dir`` from config
    2. ``STS2_HOME``
    3. ``OPENCLAW_HOME`` → ``…/sts2``
    4. ``ASTRBOT_DATA`` → ``…/sts2``
    5. ``~/.config/sts2`` (standalone / pip install)
    6. Hermes ``get_hermes_home()/sts2``
    """
    raw = (config_log_dir or "").strip()
    if raw:
        return Path(raw).expanduser()

    env_home = (os.environ.get("STS2_HOME") or "").strip()
    if env_home:
        return Path(env_home).expanduser()

    oc = (os.environ.get("OPENCLAW_HOME") or "").strip()
    if oc:
        return _sts2_subdir(Path(oc))

    ab = (os.environ.get("ASTRBOT_DATA") or "").strip()
    if ab:
        return _sts2_subdir(Path(ab))

    standalone = Path.home() / ".config" / "sts2"
    if standalone.is_dir() or (standalone / "config.yaml").is_file():
        return standalone

    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home() / "sts2"
    except Exception:
        return standalone
