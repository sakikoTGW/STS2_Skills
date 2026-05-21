"""Path and host-config resolution (no hardcoded machine profiles)."""

from __future__ import annotations

from pathlib import Path


def test_resolve_astrbot_data_dir_env(monkeypatch, tmp_path):
    from plugins.sts2.paths import resolve_astrbot_data_dir

    custom = tmp_path / "ab-data"
    monkeypatch.setenv("ASTRBOT_DATA", str(custom))
    assert resolve_astrbot_data_dir() == custom


def test_resolve_game_dir_explicit(monkeypatch, tmp_path):
    from plugins.sts2.paths import resolve_game_dir

    game = tmp_path / "Slay the Spire 2"
    game.mkdir()
    (game / "SlayTheSpire2.exe").write_text("", encoding="utf-8")
    monkeypatch.delenv("STS2_GAME_DIR", raising=False)
    assert resolve_game_dir(str(game)) == game


def test_host_config_reads_astrbot_yaml(monkeypatch, tmp_path):
    from plugins.sts2.host_config import load_sts2_section

    data = tmp_path / "AstrBot" / "data"
    cfg = data / "sts2" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        "sts2:\n  base_url: http://127.0.0.1:15526\n  pause_on_ask: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASTRBOT_DATA", str(data))
    monkeypatch.delenv("STS2_CONFIG_PATH", raising=False)
    section = load_sts2_section()
    assert section.get("base_url") == "http://127.0.0.1:15526"


def test_astrbot_bridge_has_no_hardcoded_user_profile():
    bridge = (
        Path(__file__).resolve().parents[2]
        / "plugins"
        / "sts2"
        / "integrations"
        / "astrbot"
        / "plugin"
        / "sts2_skills_bridge.py"
    )
    text = bridge.read_text(encoding="utf-8")
    assert "lczme" not in text
    assert "_ASTRBOT_DATA" not in text
    assert "_FALLBACK_SRC" not in text
    assert "Documents\\_build_tmp" not in text


def test_mcp_server_block_uses_configurable_data(tmp_path):
    from plugins.sts2.integrations.astrbot.plugin.sts2_skills_bridge import (
        mcp_server_block,
    )

    cfg = {
        "astrbot_data_dir": str(tmp_path / "ab"),
        "skills_root": str(Path(__file__).resolve().parents[2]),
        "base_url": "http://127.0.0.1:15526",
    }
    block = mcp_server_block(cfg)
    assert block["env"]["ASTRBOT_DATA"] == str(tmp_path / "ab")
    assert block["env"]["STS2_HOME"] == str(tmp_path / "ab" / "sts2")
