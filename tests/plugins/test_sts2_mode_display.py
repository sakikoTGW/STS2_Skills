"""STS2 mode display — single source of truth."""

from __future__ import annotations

import pytest


@pytest.fixture
def sts2_env(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_STS2_AUTO_RUN", raising=False)
    return home


def test_mode_mount(sts2_env, monkeypatch):
    monkeypatch.setenv("HERMES_STS2_MOUNT_MODE", "1")
    monkeypatch.delenv("HERMES_STS2_AUTO_RUN", raising=False)
    monkeypatch.delenv("HERMES_STS2_LLM_AUTOPILOT", raising=False)

    from plugins.sts2.mode_display import ensure_autoplay_running, resolve_sts2_mode

    m = resolve_sts2_mode()
    assert m["mode_id"] == "mount_mode"
    assert m["title"] == "挂载模式"
    assert m["one_shot_expected"] is True
    assert ensure_autoplay_running(reason="test")["reason"] == "mount_mode (no background autopilot)"


def test_mode_ready_when_agent_play_no_autopilot(sts2_env, monkeypatch):
    monkeypatch.setenv("HERMES_STS2_AGENT_PLAY", "1")
    monkeypatch.setenv("HERMES_STS2_LLM_AUTOPILOT", "1")

    from plugins.sts2.mode_display import resolve_sts2_mode

    m = resolve_sts2_mode()
    assert m["mode_id"] == "autopilot_ready"
    assert m["one_shot_expected"] is False


def test_ensure_autoplay_retries_when_game_down(sts2_env, monkeypatch):
    monkeypatch.setenv("HERMES_STS2_AUTO_RUN", "1")
    monkeypatch.setenv("HERMES_STS2_AGENT_PLAY", "1")

    from plugins.sts2 import client as sts2_client
    from plugins.sts2.mode_display import ensure_autoplay_running
    from unittest.mock import patch

    with patch.object(sts2_client, "ping", side_effect=ConnectionError("down")):
        r1 = ensure_autoplay_running(reason="test")
        r2 = ensure_autoplay_running(reason="test")
    assert r1.get("reason") == "game not ready"
    assert r2.get("reason") == "game not ready"
    assert r1.get("will_retry") is True


def test_mode_running_when_studying(sts2_env, monkeypatch):
    monkeypatch.setenv("HERMES_STS2_AGENT_PLAY", "1")
    from plugins.sts2.autoplay import get_controller

    ctrl = get_controller()
    ctrl._status.studying = True
    ctrl._status.running = True

    from plugins.sts2.mode_display import resolve_sts2_mode

    m = resolve_sts2_mode()
    assert m["mode_id"] == "autopilot_running"
    assert m["one_shot_expected"] is True
