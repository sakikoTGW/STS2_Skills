"""Host setup: OpenClaw merge, config defaults, CLI setup."""

from __future__ import annotations

import json
from pathlib import Path


def test_merge_openclaw_mcp_into_json(tmp_path):
    from plugins.sts2.integrations.host_setup import merge_openclaw_mcp

    oc = tmp_path / "openclaw"
    oc.mkdir()
    cfg = oc / "openclaw.json"
    cfg.write_text('{"agent": {"name": "main"}}\n', encoding="utf-8")
    block = {
        "command": "python",
        "args": ["/repo/scripts/sts2_mcp_bridge.py"],
        "env": {"STS2_HOME": str(oc / "sts2")},
    }
    path, _how = merge_openclaw_mcp(
        openclaw_home=oc,
        block=block,
        prefer_cli=False,
    )
    assert path == cfg
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "sts2" in data["mcp"]["servers"]
    assert data["mcp"]["servers"]["sts2"]["transport"] == "stdio"


def test_write_sts2_config_enforce_by_host(tmp_path):
    from plugins.sts2.integrations.host_setup import write_sts2_config

    import yaml

    ab_home = tmp_path / "ab" / "sts2"
    write_sts2_config(host="astrbot", sts2_home=ab_home, character_index=2)
    raw = yaml.safe_load((ab_home / "config.yaml").read_text(encoding="utf-8"))["sts2"]
    assert raw["enforce_single_driver"] is False

    oc_home = tmp_path / "oc"
    write_sts2_config(host="openclaw", sts2_home=oc_home, character_index=0)
    raw2 = yaml.safe_load((oc_home / "config.yaml").read_text(encoding="utf-8"))["sts2"]
    assert raw2["enforce_single_driver"] is True


def test_setup_standalone_writes_mcp_hint(tmp_path, monkeypatch):
    from plugins.sts2.integrations.host_setup import setup_host

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("STS2_HOME", raising=False)
    res = setup_host(
        "standalone",
        character_index=1,
        skip_pip=True,
        install_mod=False,
    )
    assert res.sts2_home == tmp_path / ".config" / "sts2"
    assert (res.sts2_home / "mcp.sts2.json").is_file()
