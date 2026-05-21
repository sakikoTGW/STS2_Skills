"""STS2 data-dir resolution for Hermes / OpenClaw / AstrBot."""

from __future__ import annotations

from plugins.sts2.platform_home import resolve_sts2_home


def test_sts2_home_env_wins_over_hermes(tmp_path, monkeypatch):
    custom = tmp_path / "sts2data"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setenv("STS2_HOME", str(custom))
    assert resolve_sts2_home(config_log_dir="") == custom


def test_openclaw_home_suffix(tmp_path, monkeypatch):
    oc = tmp_path / "openclaw"
    oc.mkdir()
    monkeypatch.delenv("STS2_HOME", raising=False)
    monkeypatch.setenv("OPENCLAW_HOME", str(oc))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    assert resolve_sts2_home(config_log_dir="") == oc / "sts2"


def test_config_log_dir_first(tmp_path, monkeypatch):
    explicit = tmp_path / "logs" / "sts2"
    monkeypatch.setenv("STS2_HOME", str(tmp_path / "ignored"))
    assert resolve_sts2_home(config_log_dir=str(explicit)) == explicit
