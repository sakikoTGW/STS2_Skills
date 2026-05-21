"""Runtime package version (reads pyproject.toml when not installed)."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def package_version() -> str:
    try:
        from importlib.metadata import version

        return version("sts2-skills")
    except Exception:
        import re
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        return m.group(1) if m else "0.0.0"
