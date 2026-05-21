"""Character selection for menu / new-run flow."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_character_choice():
    """Load character_choice without pulling plugins.sts2 package __init__."""
    root = Path(__file__).resolve().parents[2]
    path = root / "plugins" / "sts2" / "character_choice.py"
    spec = importlib.util.spec_from_file_location("sts2_character_choice", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_normalize_character_aliases():
    cc = _load_character_choice()
    normalize_character = cc.normalize_character
    resolve_character_setting = cc.resolve_character_setting
    CHARACTER_ZH = cc.CHARACTER_ZH

    assert normalize_character(0) == "IRONCLAD"
    assert normalize_character(1) == "SILENT"
    assert normalize_character("2") == "DEFECT"
    assert normalize_character("ironclad") == "IRONCLAD"
    assert normalize_character("IRONCLAD") == "IRONCLAD"
    assert normalize_character("静默猎手") == "SILENT"
    assert normalize_character("故障机器人") == "DEFECT"
    assert normalize_character("亡灵契约师") == "NECROBINDER"
    assert CHARACTER_ZH["REGENT"] == "储君"
    idx, canon = resolve_character_setting(3)
    assert idx == 3 and canon == "NECROBINDER"


def test_pick_character_respects_config(sts2_env, monkeypatch):
    from plugins.sts2.character_choice import pick_character_menu_action

    monkeypatch.delenv("STS2_CHARACTER", raising=False)
    opts = [
        {"option": "Ironclad", "is_locked": False},
        {"option": "Silent", "is_locked": False},
        {"option": "Defect", "is_locked": False},
    ]
    act = pick_character_menu_action(opts, cfg={"character": 1})
    assert act == {"action": "menu_select", "option": "Silent"}


def test_run_flow_picks_configured_character(sts2_env, monkeypatch):
    from plugins.sts2.run_flow import next_menu_action

    monkeypatch.setenv("STS2_CHARACTER", "2")
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

    monkeypatch.setenv("STS2_CHARACTER", "4")
    cfg = load_sts2_config()
    assert cfg["character"] == "REGENT"
    assert cfg["character_index"] == 4
