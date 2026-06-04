"""plugins.sts2.install_probe"""

from __future__ import annotations

import json
from pathlib import Path

from plugins.sts2.install_probe import check_host, check_skills, probe_install
from plugins.sts2.integrations.mcp_config import mcp_bridge_script


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
    host = tmp_path / "standalone_home"
    host.mkdir()
    bridge = mcp_bridge_script(repo_root=root)
    snippet = {
        "mcpServers": {
            "sts2": {
                "command": "python",
                "args": [str(bridge).replace("\\", "/")],
            }
        }
    }
    (host / "mcp.sts2.json").write_text(json.dumps(snippet), encoding="utf-8")
    ok, detail = check_host("standalone", host, root, game)
    assert ok is False
    assert "hint" in detail

    (host / "game_dir.txt").write_text(str(game.resolve()), encoding="utf-8")
    ok2, _ = check_host("standalone", host, root, game)
    assert ok2 is True


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
    bridge = mcp_bridge_script(repo_root=root)
    (host / "mcp.sts2.json").write_text(
        json.dumps({"mcpServers": {"sts2": {"args": [str(bridge)]}}}),
        encoding="utf-8",
    )
    ok, detail = check_host("standalone", host, root, game_b)
    assert ok is False
    assert "mismatch" in detail
