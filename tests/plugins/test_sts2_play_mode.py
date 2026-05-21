"""STS2 play_mode — on-demand LLM autopilot vs silent marathon block."""

from __future__ import annotations


def test_marathon_not_blocked_by_agent_play(monkeypatch):
    monkeypatch.delenv("HERMES_STS2_NO_MARATHON", raising=False)
    monkeypatch.delenv("HERMES_STS2_MANUAL", raising=False)
    monkeypatch.setenv("HERMES_STS2_AGENT_PLAY", "1")

    from plugins.sts2 import play_mode

    assert play_mode.marathon_forbidden() is False


def test_marathon_blocked_by_no_marathon(monkeypatch):
    monkeypatch.setenv("HERMES_STS2_NO_MARATHON", "1")
    monkeypatch.delenv("HERMES_STS2_AGENT_PLAY", raising=False)

    from plugins.sts2 import play_mode

    assert play_mode.marathon_forbidden() is True


def test_llm_marathon_allowed_when_not_forbidden(monkeypatch):
    monkeypatch.delenv("HERMES_STS2_NO_MARATHON", raising=False)
    monkeypatch.delenv("HERMES_STS2_MANUAL", raising=False)
    monkeypatch.delenv("HERMES_STS2_CHAT_THROUGH", raising=False)
    monkeypatch.delenv("HERMES_STS2_CHAT_MARATHON", raising=False)

    from plugins.sts2 import play_mode

    assert play_mode.llm_marathon_allowed() is True


def test_mount_mode_disables_background_autopilot(monkeypatch):
    monkeypatch.delenv("HERMES_STS2_NO_MARATHON", raising=False)
    monkeypatch.delenv("HERMES_STS2_LLM_AUTOPILOT", raising=False)
    monkeypatch.setenv("HERMES_STS2_MOUNT_MODE", "1")
    monkeypatch.setenv("HERMES_STS2_AGENT_PLAY", "1")

    from plugins.sts2 import play_mode

    assert play_mode.agent_play_mode() is True
    assert play_mode.llm_marathon_allowed() is False
    assert "挂载模式" in play_mode.marathon_blocked_message()


def test_act1_guard_mode_objective_default(monkeypatch):
    monkeypatch.delenv("HERMES_STS2_ACT1_GUARD", raising=False)

    from plugins.sts2.act1_policy import act1_guard_mode

    assert act1_guard_mode() in ("objective", "full", "off", "map")
