"""Cross-host path resolution and MCP env (Hermes / OpenClaw / AstrBot / standalone)."""

from __future__ import annotations

from pathlib import Path


def test_resolve_sts2_home_openclaw(monkeypatch, tmp_path):
    from plugins.sts2.platform_home import resolve_sts2_home

    oc = tmp_path / "openclaw"
    oc.mkdir()
    monkeypatch.setenv("OPENCLAW_HOME", str(oc))
    monkeypatch.delenv("STS2_HOME", raising=False)
    monkeypatch.delenv("ASTRBOT_DATA", raising=False)
    assert resolve_sts2_home() == oc / "sts2"


def test_resolve_sts2_home_standalone_before_hermes(monkeypatch, tmp_path):
    from plugins.sts2.platform_home import resolve_sts2_home

    standalone = tmp_path / ".config" / "sts2"
    standalone.mkdir(parents=True)
    (standalone / "config.yaml").write_text("sts2:\n  base_url: http://127.0.0.1:1\n", encoding="utf-8")
    monkeypatch.delenv("STS2_HOME", raising=False)
    monkeypatch.delenv("OPENCLAW_HOME", raising=False)
    monkeypatch.delenv("ASTRBOT_DATA", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert resolve_sts2_home() == standalone


def test_detect_runtime_host_from_env(monkeypatch):
    from plugins.sts2.platform_home import detect_runtime_host

    monkeypatch.setenv("ASTRBOT_DATA", "/tmp/ab")
    assert detect_runtime_host() == "astrbot"
    monkeypatch.delenv("ASTRBOT_DATA", raising=False)
    monkeypatch.setenv("OPENCLAW_HOME", "/tmp/oc")
    assert detect_runtime_host() == "openclaw"


def test_mcp_block_includes_config_path(tmp_path, monkeypatch):
    from plugins.sts2.integrations.mcp_config import astrbot_mcp_block

    data = tmp_path / "ab"
    sts2 = data / "sts2"
    sts2.mkdir(parents=True)
    (sts2 / "config.yaml").write_text(
        "sts2:\n  base_url: http://127.0.0.1:15526\n  character: 2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASTRBOT_DATA", str(data))
    block = astrbot_mcp_block(sts2_home=str(sts2), astrbot_data=str(data))
    env = block["env"]
    assert env["STS2_HOME"] == str(sts2)
    assert env["ASTRBOT_DATA"] == str(data)
    assert env["STS2_CONFIG_PATH"] == str(sts2 / "config.yaml")
    assert env.get("STS2_CHARACTER") == "2"


def test_play_mode_sts2_env_alias(monkeypatch):
    from plugins.sts2.play_mode import agent_play_mode, llm_play_enabled, mount_mode

    monkeypatch.delenv("HERMES_STS2_AGENT_PLAY", raising=False)
    monkeypatch.setenv("STS2_AGENT_PLAY", "1")
    assert agent_play_mode() is True

    monkeypatch.delenv("HERMES_STS2_MOUNT_MODE", raising=False)
    monkeypatch.setenv("STS2_MOUNT_MODE", "yes")
    assert mount_mode() is True

    monkeypatch.delenv("HERMES_STS2_LLM_PLAY", raising=False)
    monkeypatch.setenv("STS2_LLM_PLAY", "0")
    assert llm_play_enabled() is False


def test_astrbot_mcp_block_matches_mcp_config(tmp_path):
    from plugins.sts2.integrations.astrbot.plugin.sts2_skills_bridge import mcp_server_block
    from plugins.sts2.integrations.mcp_config import astrbot_mcp_block

    root = Path(__file__).resolve().parents[2]
    cfg = {
        "astrbot_data_dir": str(tmp_path / "ab"),
        "skills_root": str(root),
        "base_url": "http://127.0.0.1:15526",
        "character": 0,
    }
    direct = mcp_server_block(cfg)
    shared = astrbot_mcp_block(
        repo_root=root,
        sts2_home=str(tmp_path / "ab" / "sts2"),
        astrbot_data=str(tmp_path / "ab"),
        base_url="http://127.0.0.1:15526",
    )
    assert set(direct["env"]) <= set(shared["env"]) | {"STS2_CHARACTER"}
    assert direct["env"]["STS2_HOME"] == shared["env"]["STS2_HOME"]
