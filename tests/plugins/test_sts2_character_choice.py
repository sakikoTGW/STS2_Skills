"""Character selection for menu / new-run flow."""

from __future__ import annotations

import os


def test_normalize_character_aliases():
    from plugins.sts2.character_choice import normalize_character

    assert normalize_character("silent") == "SILENT"
    assert normalize_character("猎手") == "SILENT"
    assert normalize_character("necrobinder") == "NECROBINDER"
    assert normalize_character("necrobancer") == "NECROBINDER"


def test_pick_character_respects_config(sts2_env, monkeypatch):
    from plugins.sts2.character_choice import pick_character_menu_action

    monkeypatch.delenv("STS2_CHARACTER", raising=False)
    opts = [
        {"option": "Ironclad", "is_locked": False},
        {"option": "Silent", "is_locked": False},
        {"option": "Defect", "is_locked": False},
    ]
    act = pick_character_menu_action(opts, cfg={"character": "silent"})
    assert act == {"action": "menu_select", "option": "Silent"}


def test_run_flow_picks_configured_character(sts2_env, monkeypatch):
    from plugins.sts2.run_flow import next_menu_action

    monkeypatch.setenv("STS2_CHARACTER", "defect")
    state = {
        "state_type": "menu",
        "menu_screen": "character",
        "options": [
            {"option": "Ironclad", "enabled": True},
            {"option": "Defect", "enabled": True},
        ],
    }
    act = next_menu_action(state)
    assert act == {"action": "menu_select", "option": "Defect"}


def test_sts2_character_env_overrides_config(sts2_env, monkeypatch):
    from plugins.sts2.config import load_sts2_config

    monkeypatch.setenv("STS2_CHARACTER", "regent")
    cfg = load_sts2_config()
    assert cfg["character"] == "REGENT"
