"""AstrBot integration must not treat HTTP 200 + status:error as success."""

from __future__ import annotations

import json


def test_card_flow_sync_reports_api_error_as_failure(monkeypatch):
    from plugins.sts2.integrations.astrbot.plugin import card_pick_force

    states = [
        {"state_type": "card_reward", "cards": [{"name": "Strike"}]},
        {"state_type": "combat"},
    ]

    def fake_get(**_kw):
        return 200, states.pop(0)

    monkeypatch.setattr(
        "plugins.sts2.client.get_singleplayer_state",
        fake_get,
    )
    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda _body: (200, {"status": "error", "message": "invalid pick"}),
    )
    monkeypatch.setattr(
        "plugins.sts2.integrations.astrbot.plugin.sts2_skills_bridge.ensure_skills",
        lambda *_a, **_k: None,
    )

    out = card_pick_force.run_card_flow_until_clear_sync({}, max_steps=2)
    assert out is not None
    assert out.get("success") is False


def test_action_response_ok_matches_sts2_act_semantics():
    from plugins.sts2.client import action_response_ok

    assert action_response_ok(200, {"status": "ok"}) is True
    assert action_response_ok(200, {"status": "error", "message": "x"}) is False
    assert action_response_ok(500, {"status": "ok"}) is False
