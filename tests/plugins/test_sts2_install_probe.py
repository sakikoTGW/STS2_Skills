"""plugins.sts2.install_probe"""

from __future__ import annotations

from pathlib import Path

from plugins.sts2.install_probe import check_host, check_skills, probe_install


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


def test_check_host_requires_game_dir_hint(tmp_path):
    root = Path(__file__).resolve().parents[2]
    game = tmp_path / "game"
    game.mkdir()
    (game / "SlayTheSpire2.exe").write_bytes(b"")
    host = tmp_path / "host"
    host.mkdir()
    ok, detail = check_host("standalone", host, root, game)
    assert ok is False
    assert detail == "game_dir hint missing"

    (host / "game_dir.txt").write_text(str(game.resolve()), encoding="utf-8")
    ok2, _ = check_host("standalone", host, root, game)
    assert ok2 is False  # MCP not configured in empty host dir


def test_check_host_game_dir_mismatch(tmp_path):
    root = Path(__file__).resolve().parents[2]
    game_a = tmp_path / "game_a"
    game_b = tmp_path / "game_b"
    for g in (game_a, game_b):
        g.mkdir()
        (g / "SlayTheSpire2.exe").write_bytes(b"")
    host = tmp_path / "host"
    host.mkdir()
    (host / "game_dir.txt").write_text(str(game_a.resolve()), encoding="utf-8")
    ok, detail = check_host("standalone", host, root, game_b)
    assert ok is False
    assert detail == "game_dir mismatch"
