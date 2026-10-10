"""AstrBot runner must treat STS2MCP status:error as action failure."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def plugin_cfg():
    return {"base_url": "http://127.0.0.1:19999", "skills_dir": "/tmp/skills"}


def test_pause_recovery_reports_api_error_as_failure(plugin_cfg, monkeypatch):
    from plugins.sts2.integrations.astrbot.plugin.runner import STS2Runner

    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.runner.ensure_skills",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.runner.force_unpause_controller",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.runner.run_card_flow_until_clear",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.runner.apply_astrbot_runtime",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.runner.set_play_mode",
        lambda *a, **k: None,
    )

    ctrl = MagicMock()
    ctrl.step_once.return_value = {
        "paused": True,
        "state_type": "card_reward",
        "success": False,
    }

    runner = STS2Runner(plugin_cfg)
    runner._ctrl = ctrl

    state = {"state_type": "card_reward", "cards": []}

    async def fake_get_state():
        return state

    runner.get_state = fake_get_state  # type: ignore[method-assign]

    monkeypatch.setattr(
        "plugins.sts2.client.get_singleplayer_state",
        lambda **kw: (200, state),
    )
    monkeypatch.setattr(
        "plugins.sts2.decision.decide",
        lambda s: ("pick", {"action": "choose", "index": 0}),
    )
    monkeypatch.setattr(
        "plugins.sts2.action_validate.validate_action",
        lambda s, b: b,
    )
    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda body: (200, {"status": "error", "message": "bad index"}),
    )

    out = asyncio.run(runner.step_once())
    assert out.get("recovered_from_pause") is True
    assert out.get("success") is False
    assert out.get("body", {}).get("status") == "error"


def test_card_flow_sync_reports_api_error_as_failure(monkeypatch):
    from plugins.sts2.integrations.astrbot.plugin.card_pick_force import (
        run_card_flow_until_clear_sync,
    )

    state = {"state_type": "card_reward", "cards": [{"name": "Strike"}]}

    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.sts2_skills_bridge.ensure_skills",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "plugins.sts2.client.get_singleplayer_state",
        lambda **kw: (200, state),
    )
    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.card_pick_force.decide_card_flow",
        lambda s: ("pick", {"action": "choose", "index": 0}),
    )
    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda body: (200, {"status": "error", "message": "reject"}),
    )

    out = run_card_flow_until_clear_sync({"base_url": "http://127.0.0.1:1"})
    assert out is not None
    assert out.get("success") is False
