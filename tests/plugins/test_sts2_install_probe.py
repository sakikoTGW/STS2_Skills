"""plugins.sts2.install_probe"""

from __future__ import annotations

import json
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


def test_check_host_rejects_prefix_path_false_positive(tmp_path):
    from plugins.sts2.install_probe import _path_referenced_in_text, check_host

    skills = tmp_path / "STS2_Skills"
    skills.mkdir()
    (skills / "scripts").mkdir(parents=True)
    bridge = skills / "scripts" / "sts2_mcp_bridge.py"
    bridge.write_text("# bridge\n", encoding="utf-8")

    old_skills = tmp_path / "STS2_Skills_old"
    old_skills.mkdir()
    (old_skills / "scripts").mkdir(parents=True)
    (old_skills / "scripts" / "sts2_mcp_bridge.py").write_text("# old\n", encoding="utf-8")

    cfg = tmp_path / "mcp.sts2.json"
    cfg.write_text(
        json.dumps({"command": "python", "args": [str(old_skills / "scripts" / "sts2_mcp_bridge.py")]}),
        encoding="utf-8",
    )
    text = cfg.read_text(encoding="utf-8")
    assert _path_referenced_in_text(text, old_skills) is True
    assert _path_referenced_in_text(text, skills) is False

    ok, detail = check_host("standalone", tmp_path, skills, tmp_path / "game")
    assert ok is False
    assert detail == "mcp not configured"
