"""AstrBot integration must not treat HTTP 200 + status:error as success."""

from __future__ import annotations


def test_card_flow_reports_api_error_as_failure(monkeypatch):
    from plugins.sts2.integrations.astrbot.plugin.card_pick_force import (
        run_card_flow_until_clear_sync,
    )

    def fake_get(**_kw):
        return 200, {"state_type": "card_reward", "cards": []}

    monkeypatch.setattr(
        "plugins.sts2.client.get_singleplayer_state",
        fake_get,
    )
    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda body: (200, {"status": "error", "message": "bad pick"}),
    )
    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.card_pick_force.decide_card_flow",
        lambda _s: ("test", {"action": "select_card_reward", "card_index": 0}),
    )
    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.sts2_skills_bridge.ensure_skills",
        lambda *a, **k: None,
    )

    out = run_card_flow_until_clear_sync({})
    assert out is not None
    assert out["success"] is False
    assert out["body"]["status"] == "error"


def test_action_response_ok_matches_sts2_client():
    from plugins.sts2 import client as sts2_client

    assert sts2_client.action_response_ok(200, {"status": "ok"}) is True
    assert sts2_client.action_response_ok(200, {"status": "error"}) is False
    assert sts2_client.action_response_ok(500, {"status": "ok"}) is False
