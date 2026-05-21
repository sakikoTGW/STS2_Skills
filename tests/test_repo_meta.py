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


def test_release_notes_for_current_version() -> None:
    ver = _pyproject_version()
    path = ROOT / f"RELEASE_NOTES_v{ver}.md"
    assert path.is_file(), f"missing {path.name} (template: RELEASE_NOTES_v1.0.3.md)"
    text = path.read_text(encoding="utf-8")
    assert "## 版本策略" in text
    assert "## 下载" in text
    assert f"STS2_Skills-v{ver}.zip" in text
    assert "sts2skill.exe" in text


def test_compat_pins_sts2mcp_tag() -> None:
    import yaml

    compat = yaml.safe_load((ROOT / "compat.yaml").read_text(encoding="utf-8")) or {}
    tag = str(compat.get("sts2mcp_release_tag") or "").strip()
    assert tag, "compat.yaml must pin sts2mcp_release_tag (not latest)"


def _public_doc_paths() -> list[Path]:
    paths: list[Path] = [
        ROOT / "README.md",
        ROOT / "README.en.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        ROOT / "VERSION_MIGRATION.md",
        ROOT / "CHANGELOG.md",
        ROOT / "plugins" / "sts2" / "README.md",
    ]
    for sub in ("astrbot", "openclaw"):
        base = ROOT / "plugins" / "sts2" / "integrations" / sub
        readme = base / "README.md"
        if readme.is_file():
            paths.append(readme)
        for name in ("mcp-server.example.json",):
            example = base / name
            if example.is_file():
                paths.append(example)
    return paths


def test_public_docs_avoid_internal_phrasing() -> None:
    banned = (
        "成熟项目",
        "Cursor Agent",
        "Clash 7890",
        "internal-only",
        "standard contributor guide",
        "hermes-agent-main/scripts",
        "autopilot friendly",
    )
    for path in _public_doc_paths():
        text = path.read_text(encoding="utf-8")
        for phrase in banned:
            assert phrase not in text, f"{path.relative_to(ROOT)}: banned phrase {phrase!r}"


if __name__ == "__main__":
    test_pyproject_version_matches_compat()
    test_plugin_yaml_version()
    test_astrbot_metadata_version()
    test_compat_pins_sts2mcp_tag()
    print("OK", _pyproject_version())
