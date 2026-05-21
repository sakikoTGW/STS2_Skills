"""plugins.sts2.install_probe"""

from __future__ import annotations

from pathlib import Path

from plugins.sts2.install_probe import check_skills, probe_install


def test_check_skills_repo_root():
    root = Path(__file__).resolve().parents[2]
    ok, detail = check_skills(root)
    assert ok is True
    assert detail == "ok"


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
