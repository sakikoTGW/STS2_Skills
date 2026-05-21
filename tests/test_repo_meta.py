"""Repository metadata checks (no game / network required)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "pyproject.toml missing [project].version"
    return m.group(1)


def test_pyproject_version_matches_compat() -> None:
    import yaml

    compat = yaml.safe_load((ROOT / "compat.yaml").read_text(encoding="utf-8")) or {}
    assert compat.get("sts2_skills_version") == _pyproject_version()


def test_plugin_yaml_version() -> None:
    text = (ROOT / "plugins" / "sts2" / "plugin.yaml").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\S+)", text, re.MULTILINE)
    assert m and m.group(1) == _pyproject_version()


def test_astrbot_metadata_version() -> None:
    import yaml

    meta = yaml.safe_load(
        (
            ROOT
            / "plugins"
            / "sts2"
            / "integrations"
            / "astrbot"
            / "plugin"
            / "metadata.yaml"
        ).read_text(encoding="utf-8")
    )
    assert meta.get("version") == _pyproject_version()


def test_compat_pins_sts2mcp_tag() -> None:
    import yaml

    compat = yaml.safe_load((ROOT / "compat.yaml").read_text(encoding="utf-8")) or {}
    tag = str(compat.get("sts2mcp_release_tag") or "").strip()
    assert tag, "compat.yaml must pin sts2mcp_release_tag (not latest)"


if __name__ == "__main__":
    test_pyproject_version_matches_compat()
    test_plugin_yaml_version()
    test_astrbot_metadata_version()
    test_compat_pins_sts2mcp_tag()
    print("OK", _pyproject_version())
