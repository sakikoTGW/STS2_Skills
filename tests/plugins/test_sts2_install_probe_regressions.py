"""Regression tests for install_probe correctness."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.sts2.install_probe import _path_in_text, check_host, check_pip


def test_path_in_text_rejects_prefix_false_positive(tmp_path):
    skills = tmp_path / "STS2_Skills"
    skills.mkdir()
    stale = tmp_path / "STS2_Skills_old"
    stale.mkdir()
    text = json.dumps(
        {
            "mcpServers": {
                "sts2": {
                    "command": "python",
                    "args": [str(stale / "scripts" / "sts2_mcp_bridge.py")],
                }
            }
        }
    )
    assert _path_in_text(text, skills) is False
    assert _path_in_text(text, stale) is True


def test_check_host_rejects_stale_mcp_path(tmp_path):
    from plugins.sts2.integrations.mcp_config import mcp_bridge_script

    skills = tmp_path / "STS2_Skills"
    skills.mkdir(parents=True)
    (skills / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (skills / "plugins" / "sts2").mkdir(parents=True)
    (skills / "plugins" / "sts2" / "__init__.py").write_bytes(b"")
    (skills / "scripts").mkdir()
    bridge = mcp_bridge_script(repo_root=skills)
    bridge.parent.mkdir(parents=True, exist_ok=True)
    bridge.write_text("# bridge\n", encoding="utf-8")

    stale = tmp_path / "STS2_Skills_old"
    stale.mkdir()
    ab = tmp_path / "astrbot"
    ab.mkdir()
    (ab / "plugins" / "astrbot_plugin_sts2_agent").mkdir(parents=True)
    mcp = ab / "mcp_server.json"
    mcp.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "sts2": {
                        "command": "python",
                        "args": [str(stale / "scripts" / "sts2_mcp_bridge.py")],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    game = tmp_path / "game"
    game.mkdir()
    ok, _ = check_host("astrbot", ab, skills, game)
    assert ok is False


def test_check_pip_fails_when_python_missing(tmp_path):
    root = Path(__file__).resolve().parents[2]
    ok, detail = check_pip(root, python=str(tmp_path / "missing-python.exe"))
    assert ok is False
    assert detail == "pip/import missing"
