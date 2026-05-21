"""Host-agnostic env flags: ``HERMES_STS2_*`` (Hermes) and ``STS2_*`` (all hosts)."""

from __future__ import annotations

import os


def env_flag(*names: str) -> bool:
    for name in names:
        if os.environ.get(name, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


def env_disabled(*names: str) -> bool:
    for name in names:
        if os.environ.get(name, "").strip().lower() in ("0", "false", "no"):
            return True
    return False
