"""plugins.sts2.install_probe"""

from __future__ import annotations

from pathlib import Path

from plugins.sts2.install_probe import (
    check_pip,
    check_skills,
    probe_install,
    read_installed_version,
)


def test_check_skills_repo_root():
    root = Path(__file__).resolve().parents[2]
    ok, detail = check_skills(root)
    assert ok is True
    assert detail == "ok"


def test_read_installed_version_from_repo():
    root = Path(__file__).resolve().parents[2]
    ver = read_installed_version(root)
    assert ver and ver[0].isdigit()


def test_check_skills_rejects_version_mismatch(tmp_path):
    root = Path(__file__).resolve().parents[2]
    dst = tmp_path / "skills"
    dst.mkdir()
    for rel in ("pyproject.toml", "plugins/sts2/cli.py", "scripts/sts2_mcp_bridge.py"):
        src = root / rel
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        (dst / rel).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (dst / "pyproject.toml").write_text(
        (dst / "pyproject.toml").read_text(encoding="utf-8").replace('version = "1.0.6"', 'version = "1.0.5"'),
        encoding="utf-8",
    )
    ok, detail = check_skills(dst, expected_version="1.0.6")
    assert ok is False
    assert "mismatch" in detail


def test_check_pip_without_python_path(tmp_path):
    root = Path(__file__).resolve().parents[2]
    ok, detail = check_pip(root, python="")
    assert ok is False
    assert detail == "python not set"


def test_probe_install_repo_as_standalone(tmp_path):
    root = Path(__file__).resolve().parents[2]
    game = tmp_path / "game"
    game.mkdir()
    (game / "SlayTheSpire2.exe").write_bytes(b"")
    (game / "mods").mkdir()
    (game / "mods" / "STS2_MCP.dll").write_bytes(b"")
    r = probe_install("standalone", root, game, root)
    assert r.skills_ready
    assert r.mod_ready
