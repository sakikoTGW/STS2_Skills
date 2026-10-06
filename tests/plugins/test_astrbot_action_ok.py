"""AstrBot paths must treat STS2MCP status:error as action failure (HTTP 200)."""

from plugins.sts2 import client as sts2_client


def test_action_response_ok_rejects_non_ok_payload():
    assert sts2_client.action_response_ok(200, {"status": "ok"}) is True
    assert sts2_client.action_response_ok(200, {"status": "error", "message": "x"}) is False
    assert sts2_client.action_response_ok(200, {"status": "failed"}) is False
    assert sts2_client.action_response_ok(500, {"status": "ok"}) is False
    assert sts2_client.action_response_ok(200, "not a dict") is True


def test_card_flow_sync_reports_api_error(monkeypatch):
    from plugins.sts2.integrations.astrbot.plugin.card_pick_force import (
        run_card_flow_until_clear_sync,
    )

    state = {"state_type": "card_reward", "legal_actions": []}

    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.sts2_skills_bridge.ensure_skills",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "plugins.sts2.client.get_singleplayer_state",
        lambda **kw: (200, state),
    )
    monkeypatch.setattr(
        "plugins.sts2.card_pick_brain.rule_card_reward_fallback",
        lambda s: ("pick", {"action": "select_card_reward", "card_index": 0}),
    )
    monkeypatch.setattr(
        "plugins.sts2.action_validate.validate_action",
        lambda s, b: b,
    )
    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda body: (200, {"status": "error", "message": "bad index"}),
    )

    out = run_card_flow_until_clear_sync({}, max_steps=2)
    assert out is not None
    assert out["success"] is False
    assert out["body"]["status"] == "error"
