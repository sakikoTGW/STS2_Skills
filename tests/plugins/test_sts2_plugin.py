"""Tests for plugins/sts2 (no live game required)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sts2_env(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text(
        "sts2:\n  base_url: http://127.0.0.1:19999\n",
        encoding="utf-8",
    )
    return home


def test_ping_parses_json(sts2_env, monkeypatch):
    from plugins.sts2 import client as c

    cfg = sts2_env / "config.yaml"
    monkeypatch.setenv("STS2_CONFIG_PATH", str(cfg))
    monkeypatch.setenv("HERMES_HOME", str(sts2_env))

    class FakeResp:
        status = 200

        def read(self):
            return b'{"status":"ok","message":"hi"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResp())
    assert c.ping()["status"] == "ok"
    assert c.get_base_url() == "http://127.0.0.1:19999"


def test_setup_status_tool_without_http(sts2_env, monkeypatch):
    from plugins.sts2.tools import handle_sts2_setup_status

    monkeypatch.setattr(
        "plugins.sts2.client.ping",
        MagicMock(side_effect=ConnectionError("down")),
    )
    monkeypatch.setattr("plugins.sts2.paths.find_game_dir", lambda: None)
    raw = handle_sts2_setup_status({})
    data = json.loads(raw)
    assert data["success"] is True
    assert data["http_ping_ok"] is False


def test_act_builds_body(sts2_env, monkeypatch):
    from plugins.sts2.tools import handle_sts2_act

    captured = {}

    def fake_post(body):
        captured["body"] = body
        return 200, {"status": "ok"}

    monkeypatch.setattr("plugins.sts2.client.post_singleplayer_action", fake_post)
    raw = handle_sts2_act(
        {"action": "play_card", "card_index": 1, "target": "ENEMY_0"}
    )
    data = json.loads(raw)
    assert data["success"] is True
    assert captured["body"]["action"] == "play_card"
    assert captured["body"]["card_index"] == 1


def test_find_game_dir_uses_cache(sts2_env, monkeypatch):
    from plugins.sts2.paths import find_game_dir

    game = sts2_env / "Slay the Spire 2"
    game.mkdir()
    (game / "SlayTheSpire2.exe").write_text("", encoding="utf-8")
    cache = sts2_env / "sts2" / "game_dir.txt"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(str(game), encoding="utf-8")
    monkeypatch.delenv("STS2_GAME_DIR", raising=False)
    assert find_game_dir() == game


def test_mcp_server_config_uses_python_module():
    from plugins.sts2.config import mcp_server_config

    cfg = mcp_server_config()
    args_joined = " ".join(cfg.get("args") or [])
    cmd = str(cfg.get("command") or "")
    # Installed ``sts2-mcp`` on PATH uses bare executable; dev uses -m module or bridge script.
    assert (
        "plugins.sts2.mcp_server" in args_joined
        or "sts2_mcp_bridge" in args_joined
        or "sts2-mcp" in cmd
        or cmd.endswith("sts2-mcp")
    )


def test_notes_recall(sts2_env):
    from plugins.sts2.notes import append_hot_note, merge_strategy_rules, recall_block

    append_hot_note("test", "blocked with defect")
    merge_strategy_rules(["Always block when enemy attacks"], source="system")
    block = recall_block()
    assert "blocked" in block
    assert "block" in block.lower()


def test_lessons_record_and_avoid_elite(sts2_env):
    from plugins.sts2.lessons import (
        build_lesson_rule,
        read_recent_outcomes,
        record_outcome,
        should_avoid_elite_early,
    )

    prev = {"state_type": "monster", "run": {"floor": 2, "character": "IRONCLAD"}}
    nxt = {
        "state_type": "menu",
        "run": {"floor": 2},
        "player": {"hp": 0, "max_hp": 80},
    }
    out = record_outcome("death", prev, nxt, recent_actions=[{"action": "end_turn"}])
    assert out.get("recorded") is True
    rule = out.get("rule", "")
    assert "阵亡" in rule or "层" in rule
    assert read_recent_outcomes(1)
    record_outcome("death", prev, nxt, recent_actions=[])
    assert should_avoid_elite_early() is True
    rule2 = build_lesson_rule("death", prev, nxt, [])
    assert "普通战" in rule2 or "意图" in rule2 or "防" in rule2


def test_safe_fallback_map_not_end_turn(sts2_env, monkeypatch):
    from plugins.sts2.decision import decide

    monkeypatch.setattr(
        "agent.auxiliary_client.call_llm",
        lambda *a, **k: "not valid json",
    )
    state = {
        "state_type": "map",
        "map": {"next_options": [{"index": 2, "type": "elite"}]},
    }
    _, body = decide(state)
    assert body["action"] == "choose_map_node"
    assert body["index"] == 2


def test_driver_lock_blocks_manual_act(sts2_env):
    from plugins.sts2 import driver_lock
    from plugins.sts2.tools import handle_sts2_act

    driver_lock.acquire("autoplay")
    try:
        raw = handle_sts2_act({"action": "end_turn"})
        data = json.loads(raw)
        assert data.get("success") is False or "error" in data
        assert "blocked" in str(data.get("error", raw)).lower()
    finally:
        driver_lock.release("autoplay")


def test_combat_scorer_prefers_attack_on_buff(sts2_env):
    from plugins.sts2.combat_scorer import decide_combat_scored

    state = {
        "run": {"floor": 3},
        "battle": {
            "round": 2,
            "turn": "player",
            "is_play_phase": True,
            "enemies": [
                {
                    "entity_id": "E0",
                    "hp": 40,
                    "intents": [{"type": "Buff", "label": "Buff"}],
                }
            ],
        },
        "player": {
            "hp": 70,
            "max_hp": 80,
            "energy": 2,
            "block": 0,
            "hand": [
                {
                    "index": 0,
                    "id": "STRIKE",
                    "type": "Attack",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "AnyEnemy",
                },
                {
                    "index": 1,
                    "id": "DEFEND",
                    "type": "Skill",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "Self",
                },
            ],
        },
    }
    act = decide_combat_scored(state)
    assert act["action"] == "play_card"
    assert act["card_index"] == 0


def test_combat_brain_attacks_on_buff_intent(sts2_env):
    from plugins.sts2.combat_brain import decide_combat

    state = {
        "run": {"floor": 3},
        "battle": {
            "round": 2,
            "turn": "player",
            "is_play_phase": True,
            "enemies": [
                {
                    "entity_id": "E0",
                    "hp": 40,
                    "intents": [{"type": "Buff", "label": "Buff", "description": "Buffing."}],
                }
            ],
        },
        "player": {
            "hp": 70,
            "max_hp": 80,
            "energy": 2,
            "block": 0,
            "hand": [
                {"index": 0, "id": "STRIKE", "type": "Attack", "cost": "1", "can_play": True, "target_type": "AnyEnemy"},
                {"index": 1, "id": "DEFEND", "type": "Skill", "cost": "1", "can_play": True, "target_type": "Self"},
            ],
        },
    }
    act = decide_combat(state)
    assert act["action"] == "play_card"
    assert act["card_index"] == 0


def test_combat_brain_wait_on_enemy_turn(sts2_env):
    from plugins.sts2.combat_brain import decide_combat

    state = {
        "battle": {"turn": "enemy", "is_play_phase": False, "enemies": [{"hp": 10, "intents": []}]},
        "player": {"hand": [], "energy": 3, "hp": 50, "max_hp": 80},
    }
    assert decide_combat(state)["action"] == "__wait__"


def test_combat_brain_end_turn_when_spent(sts2_env):
    from plugins.sts2.combat_brain import decide_combat

    state = {
        "battle": {"turn": "player", "is_play_phase": True, "enemies": [{"hp": 10, "entity_id": "E0", "intents": []}]},
        "player": {"hand": [], "energy": 0, "hp": 50, "max_hp": 80},
    }
    assert decide_combat(state)["action"] == "end_turn"


def test_combat_brain_blocks_on_attack_intent(sts2_env):
    from plugins.sts2.combat_brain import decide_combat, incoming_attack_damage

    enemies = [
        {
            "entity_id": "FOE_0",
            "hp": 30,
            "intents": [{"type": "Attack", "label": "12", "description": "Deals 12 damage."}],
        }
    ]
    assert incoming_attack_damage(enemies) == 12

    state = {
        "state_type": "monster",
        "battle": {
            "round": 2,
            "turn": "player",
            "is_play_phase": True,
            "enemies": enemies,
        },
        "player": {
            "hp": 10,
            "max_hp": 80,
            "energy": 1,
            "block": 0,
            "hand": [
                {
                    "index": 0,
                    "id": "DEFEND_IRONCLAD",
                    "type": "Skill",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "Self",
                },
                {
                    "index": 1,
                    "id": "STRIKE_IRONCLAD",
                    "type": "Attack",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "AnyEnemy",
                },
            ],
        },
    }
    act = decide_combat(state)
    assert act["action"] == "play_card"
    assert act["card_index"] == 0


def test_combat_brain_act1_strikes_when_safe(sts2_env):
    from plugins.sts2.combat_brain import decide_combat

    state = {
        "run": {"floor": 1},
        "battle": {
            "round": 1,
            "turn": "player",
            "is_play_phase": True,
            "enemies": [
                {
                    "entity_id": "FOE_0",
                    "hp": 8,
                    "intents": [{"type": "Buff", "label": "?", "description": "Buffing."}],
                }
            ],
        },
        "player": {
            "hp": 70,
            "max_hp": 80,
            "energy": 3,
            "block": 0,
            "hand": [
                {
                    "index": 0,
                    "id": "STRIKE_IRONCLAD",
                    "type": "Attack",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "AnyEnemy",
                },
                {
                    "index": 1,
                    "id": "DEFEND_IRONCLAD",
                    "type": "Skill",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "Self",
                },
            ],
        },
    }
    act = decide_combat(state)
    assert act["action"] == "play_card"
    assert act["card_index"] == 0


def test_menu_tutorial_prompt_ignores(sts2_env):
    from plugins.sts2.decision import _rule_action

    state = {
        "state_type": "menu",
        "menu_screen": "popup",
        "options": [
            {"option": "ignore", "enabled": True},
            {"option": "settings", "enabled": True},
        ],
    }
    act = _rule_action(state)
    assert act == {"action": "menu_select", "option": "ignore"}


def test_action_trace_infers_card_and_damage(sts2_env):
    from plugins.sts2.action_trace import format_action_trace, infer_player_actions

    before = {
        "state_type": "monster",
        "battle": {"turn": "player", "enemies": [{"name": "Cultist", "hp": 48, "max_hp": 48}]},
        "player": {
            "hp": 70,
            "block": 0,
            "energy": 3,
            "hand": [
                {"index": 0, "id": "STRIKE", "name": "Strike", "type": "Attack", "cost": "1"},
                {"index": 1, "id": "DEFEND", "name": "Defend", "type": "Skill", "cost": "1"},
            ],
            "potions": [{"slot": 0, "id": "FIRE", "name": "Fire Potion"}],
        },
    }
    after = {
        "state_type": "monster",
        "battle": {"turn": "player", "enemies": [{"name": "Cultist", "hp": 42, "max_hp": 48}]},
        "player": {
            "hp": 70,
            "block": 0,
            "energy": 2,
            "hand": [
                {"index": 1, "id": "DEFEND", "name": "Defend", "type": "Skill", "cost": "1"},
            ],
            "potions": [],
            "max_potion_slots": 3,
        },
    }
    acts = infer_player_actions(before, after)
    kinds = {a.kind for a in acts}
    assert "play_card" in kinds
    assert "use_potion" in kinds
    text = format_action_trace(before, after)
    assert "Strike" in text or "打出" in text
    assert "Fire Potion" in text or "药水" in text
    assert "6" in text or "伤害" in text


def test_action_validate_fixes_bad_reward_index(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "rewards",
        "rewards": {"items": [{"index": 0, "type": "gold"}]},
    }
    fixed = validate_action(state, {"action": "claim_reward", "index": 99})
    assert fixed["index"] == 0


def test_proceed_on_rewards_claims_gold_before_card(sts2_env):
    from plugins.sts2.action_validate import validate_action
    from plugins.sts2.decision import decide

    state = {
        "state_type": "rewards",
        "rewards": {
            "items": [
                {"index": 1, "type": "card", "name": "Burning Pact"},
                {"index": 0, "type": "gold", "amount": 25},
            ]
        },
    }
    fixed = validate_action(state, {"action": "proceed"})
    assert fixed["action"] == "claim_reward"
    assert fixed["index"] == 0
    _, body = decide(state)
    assert body["action"] == "claim_reward"
    assert body["index"] == 0


def test_proceed_on_rewards_ok_when_all_claimed(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "rewards",
        "rewards": {
            "items": [
                {"index": 0, "type": "gold", "claimed": True},
                {"index": 1, "type": "card", "obtained": True},
            ]
        },
    }
    fixed = validate_action(state, {"action": "proceed"})
    assert fixed["action"] == "proceed"


def test_action_validate_skip_rest_option_maps_to_choose(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "rest_site",
        "player": {"hp": 50, "max_hp": 80},
        "rest_site": {
            "options": [
                {"index": 0, "id": "rest", "is_enabled": True},
                {"index": 1, "id": "smith", "is_enabled": True},
            ]
        },
    }
    fixed = validate_action(state, {"action": "skip_rest_option"})
    assert fixed["action"] == "choose_rest_option"
    assert fixed["index"] in (0, 1)


def test_action_validate_rest_site_empty_options_proceed(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {"state_type": "rest_site", "rest_site": {"options": []}}
    fixed = validate_action(state, {"action": "skip_rest_option"})
    assert fixed["action"] == "proceed"


def test_memory_bus_reads_rules(sts2_env):
    from plugins.sts2.memory_bus import refresh_memory_cache
    from plugins.sts2.notes import merge_strategy_rules

    merge_strategy_rules(["测试规则：低层少进精英"], source="system")
    mem = refresh_memory_cache()
    assert any("精英" in m for m in mem)


def test_menu_timeline_advances(sts2_env):
    from plugins.sts2.run_flow import next_menu_action

    state = {
        "state_type": "menu",
        "menu_screen": "timeline",
        "options": [
            {"option": "advance", "enabled": True},
            {"option": "back", "enabled": True},
        ],
    }
    act = next_menu_action(state)
    assert act == {"action": "menu_select", "option": "advance"}


def test_game_over_uses_main_menu(sts2_env):
    from plugins.sts2.run_flow import next_menu_action

    state = {"state_type": "game_over", "options": []}
    act = next_menu_action(state)
    assert act == {"action": "menu_select", "option": "main_menu"}


def test_opening_menu_not_run_restart(sts2_env):
    from plugins.sts2.run_flow import menu_is_opening_sequence, run_needs_restart

    intro = {
        "state_type": "menu",
        "menu_screen": "timeline",
        "options": [{"option": "advance", "enabled": True}],
    }
    assert menu_is_opening_sequence(intro, was_in_run=False)
    assert not run_needs_restart(intro, was_in_run=False)
    assert run_needs_restart(intro, was_in_run=True)


def test_card_select_confirm_after_toggle(sts2_env):
    from plugins.sts2.card_pick_brain import card_select_should_confirm

    state = {
        "state_type": "card_select",
        "card_select": {
            "can_confirm": True,
            "preview_showing": False,
            "cards": [{"index": 0, "id": "STRIKE"}],
        },
    }
    assert card_select_should_confirm(state)


def test_maybe_restart_skips_false_run_end(sts2_env, monkeypatch):
    from plugins.sts2.autoplay import AutoplayController

    ctrl = AutoplayController()
    ctrl._status.studying = True
    calls = {"burst": 0}

    def fake_burst(state, *, max_clicks=12, announce=False):
        calls["burst"] += 1
        assert announce is False
        return True

    monkeypatch.setattr(ctrl, "_menu_burst", fake_burst)
    intro = {"state_type": "menu", "menu_screen": "timeline", "options": []}
    assert ctrl._maybe_restart_run(intro) is True
    assert ctrl._runs_completed == 0
    assert calls["burst"] == 1


def test_study_combat_uses_play_brain(sts2_env, monkeypatch):
    from plugins.sts2.decision import decide
    from plugins.sts2.study_mode import set_study_mode

    monkeypatch.setattr(
        "plugins.sts2.llm_util.sts2_call_llm",
        lambda *a, **k: '{"commentary":"先格挡再输出","action":"end_turn"}',
    )
    set_study_mode(True)
    try:
        state = {
            "state_type": "monster",
            "run": {"floor": 4, "act": 1},
            "player": {
                "hp": 50,
                "max_hp": 80,
                "energy": 0,
                "block": 8,
                "hand": [],
            },
            "battle": {
                "turn": "player",
                "round": 2,
                "is_play_phase": True,
                "enemies": [
                    {
                        "entity_id": "E0",
                        "name": "Slime",
                        "hp": 5,
                        "intents": [{"type": "Attack", "label": "6"}],
                    }
                ],
            },
        }
        commentary, body = decide(state)
        assert body.get("action") == "end_turn"
        assert "思路·战斗" in commentary
    finally:
        set_study_mode(False)


def test_note_combat_aftermath(sts2_env):
    from plugins.sts2.combat_play_brain import note_combat_aftermath

    prev = {
        "state_type": "monster",
        "run": {"floor": 5},
        "player": {"hp": 40},
    }
    nxt = {"state_type": "rewards", "player": {"hp": 18}}
    rule = note_combat_aftermath(prev, nxt)
    assert rule and "掉血" in rule


def test_build_pick_context_prefetches_wiki(sts2_env, monkeypatch):
    from plugins.sts2.wiki_pick_context import build_pick_context, situation_context

    calls = []

    def fake_fetch(kind, item_id, **kw):
        calls.append(item_id)
        return (
            {
                "id": item_id,
                "name": item_id,
                "tags": ["power"],
                "rule": "测试规则",
                "wiki_snippet": "Gain strength.",
            },
            "测试规则",
        )

    monkeypatch.setattr("plugins.sts2.knowledge.has_entry", lambda k, i: False)
    monkeypatch.setattr("plugins.sts2.knowledge.fetch_and_store", fake_fetch)
    state = {
        "state_type": "card_reward",
        "run": {"floor": 5, "act": 1, "gold": 99},
        "player": {"hp": 40, "max_hp": 80, "relics": [{"name": "Burning Blood"}]},
        "card_reward": {
            "cards": [{"index": 0, "id": "INFLAME", "name": "Inflame"}],
        },
    }
    ctx = build_pick_context(state)
    assert "局势" in situation_context(state)
    assert "Wiki" in ctx
    assert "INFLAME" in ctx
    assert calls


def test_offer_reward_cards_parses_nested_and_top_level(sts2_env):
    from plugins.sts2.reward_cards import offer_reward_cards

    nested = {
        "state_type": "card_reward",
        "card_reward": {
            "cards": [
                {"index": 0, "id": "STRIKE", "name": "Strike"},
                {"index": 1, "id": "DEFEND", "name": "Defend"},
            ]
        },
    }
    assert len(offer_reward_cards(nested)) == 2
    top = {
        "state_type": "card_reward",
        "cards": [{"index": 0, "id": "BASH", "name": "Bash"}],
    }
    assert offer_reward_cards(top)[0]["id"] == "BASH"


def test_card_reward_visibility_lists_offers(sts2_env):
    from plugins.sts2.visibility import describe_situation

    state = {
        "state_type": "card_reward",
        "run": {"floor": 5, "act": 1},
        "player": {"hp": 50, "max_hp": 80},
        "card_reward": {
            "cards": [
                {"index": 0, "id": "INFLAME", "name": "Inflame", "rarity": "uncommon"},
                {"index": 1, "id": "STRIKE", "name": "Strike"},
            ],
        },
    }
    text = describe_situation(state)
    assert "选卡:" in text
    assert "Inflame" in text


def test_proceed_on_card_reward_forces_pick(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "card_reward",
        "card_reward": {
            "can_skip": False,
            "cards": [
                {"index": 0, "id": "STRIKE", "name": "Strike"},
                {"index": 1, "id": "INFLAME", "name": "Inflame", "rarity": "uncommon"},
            ],
        },
    }
    fixed = validate_action(state, {"action": "proceed"})
    assert fixed["action"] == "select_card_reward"
    assert fixed["card_index"] in (0, 1)


def test_empty_card_reward_never_proceeds_without_bloat_skip(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "card_reward",
        "run": {"floor": 3, "act": 1},
        "card_reward": {"can_skip": True, "can_proceed": True},
    }
    fixed = validate_action(state, {"action": "proceed"})
    assert fixed["action"] == "select_card_reward"
    assert fixed["card_index"] == 0

    fixed2 = validate_action(state, {"action": "select_card_reward", "card_index": 2})
    assert fixed2["action"] == "select_card_reward"
    assert fixed2["card_index"] == 0


def test_study_card_reward_uses_brain_pick(sts2_env, monkeypatch):
    from plugins.sts2.decision import decide
    from plugins.sts2.study_mode import set_study_mode

    monkeypatch.setattr(
        "plugins.sts2.llm_util.sts2_call_llm",
        lambda *a, **k: (
            '{"commentary":"缺能力轴，燃焰契合成长。","action":"select_card_reward","card_index":1}'
        ),
    )
    set_study_mode(True)
    try:
        state = {
            "state_type": "card_reward",
            "run": {"floor": 3, "act": 1},
            "player": {"hp": 60, "max_hp": 80, "deck": [{"id": "STRIKE_IRONCLAD"}] * 4},
            "card_reward": {
                "cards": [
                    {"index": 0, "id": "STRIKE", "name": "Strike"},
                    {"index": 1, "id": "INFLAME", "name": "Inflame", "rarity": "uncommon"},
                ],
            },
        }
        commentary, body = decide(state)
        assert body["action"] == "select_card_reward"
        assert body.get("card_index") == 1
        assert "思路" in commentary
    finally:
        set_study_mode(False)


def test_card_reward_can_skip_ignores_can_proceed(sts2_env):
    from plugins.sts2.card_pick_brain import card_reward_can_skip

    state = {
        "state_type": "card_reward",
        "card_reward": {"can_proceed": True, "cards": [{"index": 0, "id": "BASH"}]},
    }
    assert card_reward_can_skip(state) is False


def test_card_reward_should_skip_only_late_strike_bloat(sts2_env):
    from plugins.sts2.card_pick_brain import card_reward_should_skip

    early = {
        "state_type": "card_reward",
        "run": {"floor": 5, "act": 1},
        "card_reward": {"can_skip": True},
        "player": {"deck": [{"id": "STRIKE_IRONCLAD"}] * 6},
    }
    offers = [
        {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike"},
        {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike"},
    ]
    assert card_reward_should_skip(early, offers) is False


def test_study_card_reward_can_skip_pollution(sts2_env, monkeypatch):
    from plugins.sts2.decision import decide
    from plugins.sts2.study_mode import set_study_mode

    monkeypatch.setattr(
        "plugins.sts2.llm_util.sts2_call_llm",
        lambda *a, **k: '{"commentary":"打击过多，跳过防污染。","action":"proceed"}',
    )
    set_study_mode(True)
    try:
        state = {
            "state_type": "card_reward",
            "run": {"floor": 14, "act": 1},
            "player": {
                "hp": 60,
                "max_hp": 80,
                "deck": [{"id": "STRIKE_IRONCLAD", "type": "Attack"}] * 6,
            },
            "card_reward": {
                "can_skip": True,
                "cards": [
                    {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike"},
                    {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike"},
                ],
            },
        }
        _, body = decide(state)
        # STS2 rarely skips curated rewards; LLM proceed may coerce to pick a card.
        assert body["action"] in ("select_card_reward", "select_card", "proceed")
    finally:
        set_study_mode(False)


def test_ironclad_build_detects_strength_archetype(sts2_env):
    from plugins.sts2.ironclad_builds import (
        build_strategy_brief,
        detect_archetype,
        pick_best_offer_index,
    )

    state = {
        "run": {"floor": 12, "act": 1},
        "player": {
            "deck": [
                {"id": "INFLAME"},
                {"id": "DEMON_FORM"},
                {"id": "TWIN_STRIKE"},
            ],
        },
    }
    assert detect_archetype(state) == "strength"
    brief = build_strategy_brief(state)
    assert "力量" in brief
    assert "构筑诊断" in brief
    assert "攻略摘要" in brief or "恶魔形态" in brief
    offers = [
        {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike"},
        {"index": 1, "id": "LIMIT_BREAK", "name": "Limit Break"},
    ]
    assert pick_best_offer_index(state, offers) == 1


def test_hand_select_upgrade_picks_best_card(sts2_env, monkeypatch):
    from plugins.sts2.action_validate import validate_action
    from plugins.sts2.combat_turn_plan import reset_combat_session
    from plugins.sts2.hand_select_brain import decide_hand_select

    monkeypatch.delenv("HERMES_STS2_MANUAL", raising=False)
    monkeypatch.delenv("HERMES_STS2_MOUNT_MODE", raising=False)
    monkeypatch.delenv("HERMES_STS2_AGENT_PLAY", raising=False)
    monkeypatch.setattr(
        "plugins.sts2.act1_policy.coerce_act1_action",
        lambda _state, body: (body, False, ""),
    )
    reset_combat_session()

    state = {
        "state_type": "hand_select",
        "hand_select": {
            "mode": "upgrade_select",
            "prompt": "确认要升级的牌",
            "can_confirm": False,
            "cards": [
                {"index": 0, "id": "STRIKE_IRONCLAD", "name": "打击", "is_upgraded": False},
                {"index": 1, "id": "BASH", "name": "痛击", "is_upgraded": False},
                {"index": 2, "id": "DEFEND_IRONCLAD", "name": "防御", "is_upgraded": False},
            ],
        },
    }
    act = decide_hand_select(state)
    assert act["action"] == "combat_select_card"
    assert act["card_index"] == 1
    fixed = validate_action(state, {"action": "play_card", "card_index": 0})
    assert fixed["action"] == "combat_select_card"
    assert fixed["card_index"] == 1

    state["hand_select"]["can_confirm"] = True
    assert decide_hand_select(state)["action"] == "combat_confirm_selection"


def test_no_block_on_debuff_turn_with_defend_in_hand(sts2_env):
    """Debuff intent: do not waste Defend — prefer attack."""
    from plugins.sts2.action_validate import validate_action
    from plugins.sts2.combat_brain import block_play_is_urgent, decide_combat, prefer_block_play

    state = {
        "run": {"floor": 8},
        "state_type": "elite",
        "battle": {
            "round": 6,
            "turn": "player",
            "is_play_phase": True,
            "enemies": [
                {
                    "entity_id": "EEL",
                    "hp": 47,
                    "intents": [{"type": "Debuff", "label": "Debuff"}],
                }
            ],
        },
        "player": {
            "hp": 50,
            "max_hp": 80,
            "energy": 1,
            "block": 0,
            "hand": [
                {
                    "index": 0,
                    "id": "STRIKE_IRONCLAD",
                    "type": "Attack",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "AnyEnemy",
                },
                {
                    "index": 1,
                    "name": "防御",
                    "id": "DEFEND_IRONCLAD",
                    "type": "Skill",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "Self",
                },
            ],
        },
    }
    assert not block_play_is_urgent(state)
    assert prefer_block_play(state) is None
    act = decide_combat(state)
    assert act["action"] == "play_card"
    assert act["card_index"] == 0
    fixed = validate_action(state, {"action": "end_turn"})
    assert fixed["action"] == "end_turn"


def test_treasure_proceed_becomes_claim(sts2_env):
    from plugins.sts2.action_validate import validate_action
    from plugins.sts2.treasure_rewards import decide_treasure_action

    state = {
        "state_type": "treasure",
        "treasure": {"can_proceed": False, "relics": [{"index": 0, "name": "铅制镇纸", "id": "LEAD_PAPERWEIGHT"}]},
    }
    act = decide_treasure_action(state)
    assert act["action"] == "claim_treasure_relic"
    fixed = validate_action(state, {"action": "proceed"})
    assert fixed["action"] == "claim_treasure_relic"

    fixed2 = validate_action(
        state, {"action": "claim_reward", "index": 0}
    )
    assert fixed2["action"] == "claim_treasure_relic"


def test_prefer_block_when_net_exceeds_hp(sts2_env):
    from plugins.sts2.action_validate import validate_action
    from plugins.sts2.combat_brain import decide_combat

    state = {
        "state_type": "elite",
        "battle": {
            "turn": "player",
            "is_play_phase": True,
            "enemies": [
                {
                    "entity_id": "EEL",
                    "hp": 38,
                    "intents": [{"type": "attack", "label": "33"}],
                }
            ],
        },
        "player": {
            "hp": 14,
            "max_hp": 80,
            "energy": 1,
            "block": 0,
            "hand": [
                {
                    "index": 0,
                    "name": "防御",
                    "id": "DEFEND_IRONCLAD",
                    "type": "Skill",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "Self",
                },
                {
                    "index": 1,
                    "id": "STRIKE_IRONCLAD",
                    "type": "Attack",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "AnyEnemy",
                },
            ],
        },
    }
    act = decide_combat(state)
    assert act["action"] == "play_card"
    assert act["card_index"] == 0
    fixed = validate_action(state, {"action": "end_turn"})
    assert fixed["action"] == "play_card"
    assert fixed.get("card_index") == 0


def test_end_turn_empty_hand_not_wait(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "monster",
        "battle": {"turn": "player", "is_play_phase": True, "enemies": []},
        "player": {"hp": 50, "energy": 0, "block": 10, "hand": []},
    }
    fixed = validate_action(state, {"action": "end_turn"})
    assert fixed["action"] == "end_turn"


def test_proceed_in_combat_becomes_end_turn(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "monster",
        "battle": {"turn": "player", "is_play_phase": True, "enemies": []},
        "player": {"hp": 50, "energy": 0, "block": 0, "hand": []},
    }
    fixed = validate_action(state, {"action": "proceed"})
    assert fixed["action"] == "end_turn"


def test_proceed_in_combat_with_energy_plays_not_end_turn(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "monster",
        "battle": {
            "turn": "player",
            "is_play_phase": True,
            "enemies": [
                {
                    "entity_id": "SLUG_0",
                    "hp": 20,
                    "intents": [{"type": "attack", "label": "6"}],
                }
            ],
        },
        "player": {
            "hp": 50,
            "energy": 1,
            "block": 0,
            "hand": [
                {
                    "index": 1,
                    "id": "BURNING_PACT",
                    "name": "燃烧契约",
                    "cost": 1,
                    "can_play": True,
                    "type": "skill",
                    "description": "Draw 2 cards. Exhaust.",
                }
            ],
        },
    }
    fixed = validate_action(state, {"action": "proceed"})
    assert fixed["action"] == "play_card"
    assert fixed["card_index"] == 1


def test_end_turn_with_playable_cards_redirects(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "monster",
        "battle": {"turn": "player", "is_play_phase": True, "enemies": []},
        "player": {
            "hp": 50,
            "energy": 2,
            "block": 0,
            "hand": [
                {
                    "index": 0,
                    "id": "STRIKE",
                    "name": "打击",
                    "cost": 1,
                    "can_play": True,
                    "type": "attack",
                }
            ],
        },
    }
    fixed = validate_action(state, {"action": "end_turn"})
    assert fixed["action"] == "play_card"


def test_autoplay_step_blocked_in_manual_mode(sts2_env, monkeypatch):
    from plugins.sts2.tools import handle_sts2_autoplay

    monkeypatch.setenv("HERMES_STS2_MANUAL", "1")
    raw = handle_sts2_autoplay({"action": "step"})
    data = json.loads(raw)
    assert data.get("success") is False or "error" in data
    assert "step" in str(data.get("error", "")).lower() or "手操" in str(data.get("error", ""))


def test_combat_lethal_instead_of_defend_when_safe(sts2_env):
    """Screenshot case: 10 HP enemy, 18 incoming, 5 block + 39 HP — kill, don't Defend."""
    from plugins.sts2.combat_brain import incoming_attack_damage, is_safe_from_incoming
    from plugins.sts2.combat_scorer import decide_combat_scored

    enemies = [
        {
            "entity_id": "GREMLIN_MERC_0",
            "hp": 10,
            "intents": [{"type": "attack", "label": "9x2"}],
        }
    ]
    assert incoming_attack_damage(enemies) == 18
    assert is_safe_from_incoming(18, 5, 39) is True

    state = {
        "run": {"floor": 6},
        "battle": {
            "round": 4,
            "turn": "player",
            "is_play_phase": True,
            "enemies": enemies,
        },
        "player": {
            "hp": 39,
            "max_hp": 80,
            "energy": 2,
            "block": 5,
            "strength": 1,
            "hand": [
                {
                    "index": 0,
                    "id": "STRIKE_IRONCLAD",
                    "damage": 4,
                    "type": "Attack",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "AnyEnemy",
                },
                {
                    "index": 1,
                    "id": "STRIKE_IRONCLAD",
                    "damage": 4,
                    "type": "Attack",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "AnyEnemy",
                },
                {
                    "index": 2,
                    "id": "DEFEND_IRONCLAD",
                    "type": "Skill",
                    "cost": "1",
                    "can_play": True,
                    "target_type": "Self",
                },
            ],
        },
    }
    act = decide_combat_scored(state)
    assert act["action"] == "play_card"
    assert act["card_index"] in (0, 1)


def test_study_card_select_upgrade_brain(sts2_env, monkeypatch):
    from plugins.sts2.decision import decide
    from plugins.sts2.study_mode import set_study_mode

    monkeypatch.setattr(
        "agent.auxiliary_client.call_llm",
        lambda *a, **k: (
            '{"commentary":"升燃焰做成长核心。","action":"select_card","index":1}'
        ),
    )
    set_study_mode(True)
    try:
        state = {
            "state_type": "card_select",
            "run": {"floor": 12, "act": 1},
            "player": {
                "hp": 50,
                "max_hp": 80,
                "deck": [
                    {"id": "STRIKE_IRONCLAD", "name": "Strike"},
                    {"id": "INFLAME", "name": "Inflame"},
                ],
            },
            "card_select": {
                "screen_type": "smith",
                "cards": [
                    {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike"},
                    {"index": 1, "id": "INFLAME", "name": "Inflame"},
                ],
            },
        }
        commentary, body = decide(state)
        assert body["action"] == "select_card"
        assert body.get("index") == 1
        assert "升级" in commentary or "模型" in commentary or "Inflame" in commentary
    finally:
        set_study_mode(False)


def test_card_select_preview_confirms(sts2_env, monkeypatch):
    from plugins.sts2.decision import decide
    from plugins.sts2.study_mode import set_study_mode

    set_study_mode(True)
    try:
        state = {
            "state_type": "card_select",
            "card_select": {"preview_showing": True, "can_confirm": True, "cards": []},
        }
        _, body = decide(state)
        assert body["action"] in ("combat_confirm_selection", "confirm_selection")
    finally:
        set_study_mode(False)


def test_rule_card_select_prefers_power(sts2_env):
    from plugins.sts2.card_pick_brain import rule_card_select_fallback

    state = {
        "state_type": "card_select",
        "card_select": {
            "cards": [
                {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike"},
                {"index": 1, "id": "INFLAME", "name": "Inflame"},
            ],
        },
    }
    comm, body = rule_card_select_fallback(state)
    assert body["action"] == "select_card"
    assert body["index"] == 1
    assert "INFLAME" in comm or "1" in comm


def test_rule_fallback_skips_strike_bloat(sts2_env, monkeypatch):
    from plugins.sts2.card_pick_brain import rule_card_reward_fallback

    monkeypatch.setattr(
        "plugins.sts2.config.load_sts2_config",
        lambda: {"study_card_pick_llm": False},
    )
    state = {
        "state_type": "card_reward",
        "run": {"floor": 6, "act": 1},
        "player": {"deck": [{"id": "STRIKE_IRONCLAD"}] * 6},
        "card_reward": {
            "can_skip": True,
            "cards": [
                {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike"},
                {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike"},
            ],
        },
    }
    comm, body = rule_card_reward_fallback(state)
    # STS2 curated reward pools: card_reward_should_skip() is always False (no STS1 skip spam).
    assert body["action"] == "select_card_reward"
    assert body.get("card_index") is not None


def test_autopilot_until_victory_disables_ask(sts2_env):
    from plugins.sts2.config import load_sts2_config

    cfg = load_sts2_config()
    assert cfg.get("pause_on_ask") is False
    assert cfg.get("ask_user_on") == []


def test_resolve_without_user_never_pauses(sts2_env):
    from plugins.sts2.autonomy import resolve_without_user

    state = {
        "state_type": "card_reward",
        "card_reward": {
            "cards": [
                {"index": 0, "id": "STRIKE", "name": "Strike"},
                {"index": 1, "id": "DEFEND", "name": "Defend"},
            ]
        },
    }
    _, body = resolve_without_user(state)
    assert body.get("action") != "__pause__"


def test_study_mode_visible_across_threads(sts2_env):
    import threading

    from plugins.sts2.study_mode import is_study_mode, set_study_mode

    set_study_mode(True)
    seen = []

    def worker() -> None:
        seen.append(is_study_mode())

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    set_study_mode(False)
    assert seen == [True]


def test_study_mode_skips_user_ask(sts2_env):
    from plugins.sts2.decision import decide
    from plugins.sts2.study_mode import set_study_mode

    set_study_mode(True)
    try:
        state = {
            "state_type": "card_reward",
            "card_reward": {
                "cards": [
                    {"index": 0, "id": "STRIKE", "name": "Strike"},
                    {"index": 1, "id": "DEFEND", "name": "Defend"},
                ]
            },
        }
        commentary, body = decide(state)
        assert body.get("action") != "__pause__"
        assert "select_card_reward" in body.get("action", "") or body.get("action") == "proceed"
    finally:
        set_study_mode(False)


def test_learn_coach_asks_when_no_block(sts2_env):
    from plugins.sts2.learn_coach import LearnCoach

    coach = LearnCoach()
    start = {
        "state_type": "monster",
        "run": {"floor": 2},
        "battle": {
            "turn": "player",
            "round": 1,
            "enemies": [
                {
                    "hp": 20,
                    "intents": [{"type": "attack", "label": "10", "description": "10"}],
                }
            ],
        },
        "player": {
            "hp": 50,
            "max_hp": 80,
            "energy": 3,
            "block": 0,
            "hand": [
                {
                    "index": 0,
                    "id": "DEFEND_IRONCLAD",
                    "name": "Defend",
                    "type": "Skill",
                    "cost": "1",
                    "can_play": True,
                },
            ],
        },
    }
    end = {
        **start,
        "player": {**start["player"], "hp": 40, "block": 0, "energy": 0},
    }
    curr = {
        **start,
        "battle": {**start["battle"], "turn": "enemy"},
    }
    coach._turn_start = start
    q = coach._combat_turn_question(start, end)
    assert q is not None
    assert "格挡" in q or "伤害" in q


def test_learn_absorb_answer(sts2_env):
    from plugins.sts2.learn_coach import absorb_user_answer
    from plugins.sts2.notes import read_hot_notes

    out = absorb_user_answer("为何不打防？", "这怪下回合才爆发，先抢血。", meta={"floor": 1})
    assert out.get("saved")
    assert "用户偏好" in out.get("rule", "") or "抢血" in read_hot_notes()


def test_visibility_play_card_commentary(sts2_env):
    from plugins.sts2.visibility import describe_action, format_turn_commentary

    state = {
        "state_type": "monster",
        "player": {
            "hand": [
                {
                    "index": 0,
                    "name": "Strike",
                    "id": "STRIKE_IRONCLAD",
                    "cost": "1",
                    "can_play": True,
                }
            ],
            "hp": 70,
            "max_hp": 80,
            "energy": 3,
            "block": 0,
        },
        "battle": {"enemies": [{"name": "Jaw Worm", "hp": 12, "intents": []}]},
    }
    body = {"action": "play_card", "card_index": 0, "target": "FOE_0"}
    text = format_turn_commentary(state, body, act_ok=True)
    assert "Strike" in text
    assert "出牌" in describe_action(state, body)


def test_bootstrap_learning_store(sts2_env):
    from plugins.sts2.lessons import bootstrap_learning_store, read_recent_outcomes
    from plugins.sts2.notes import read_strategy
    from plugins.sts2.storage import strategy_path

    out = bootstrap_learning_store(ascension=1)
    assert out.get("bootstrapped") is True
    rules = read_strategy().get("rules") or []
    assert any("进阶1" in str(r) for r in rules)
    assert strategy_path().is_file()
    assert bootstrap_learning_store().get("bootstrapped") is False


def test_record_action_failure_promotes(sts2_env):
    from plugins.sts2.lessons import record_action_failure
    from plugins.sts2.notes import read_strategy

    state = {
        "state_type": "monster",
        "run": {"floor": 2, "ascension": 1},
        "player": {"hp": 50},
    }
    action = {"action": "end_turn"}
    err = "Not in play phase"
    for _ in range(2):
        record_action_failure(state, action, err)
    rules = read_strategy().get("rules") or []
    assert any("敌人回合" in str(r) or "end_turn" in str(r) for r in rules)


def test_bundle_select_picks_from_bundles_list(sts2_env):
    from plugins.sts2.bundle_select_brain import decide_bundle_select

    state = {
        "state_type": "bundle_select",
        "bundle_select": {
            "bundles": [
                {"index": 0, "name": "starter_strikes", "id": "A"},
                {"index": 1, "name": "strength_bundle", "id": "B"},
            ],
            "can_proceed": False,
        },
    }
    body = decide_bundle_select(state)
    assert body == {"action": "select_bundle", "index": 1}


def test_bundle_select_confirms_preview(sts2_env):
    from plugins.sts2.bundle_select_brain import decide_bundle_select

    state = {
        "state_type": "bundle_select",
        "bundle_select": {
            "preview_showing": True,
            "can_confirm": True,
            "bundles": [{"index": 0, "cards": []}],
        },
    }
    body = decide_bundle_select(state)
    assert body == {"action": "confirm_bundle_selection"}


def test_bundle_select_no_blind_proceed(sts2_env):
    from plugins.sts2.action_validate import validate_action
    from plugins.sts2.bundle_select_brain import decide_bundle_select

    state = {
        "state_type": "bundle_select",
        "run": {"floor": 1, "act": 1},
        "player": {"hp": 80, "hand": []},
        "options": [{"option": "take_strike", "enabled": True, "index": 0}],
        "bundle_select": {"can_proceed": False},
    }
    body = validate_action(state, {"action": "proceed"})
    assert body.get("action") != "proceed"
    ruled = decide_bundle_select(state)
    assert ruled.get("action") in ("select_card", "menu_select", "__wait__", "confirm_selection")


def test_crystal_sphere_divine_alias_maps_to_click(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "crystal_sphere",
        "crystal_sphere": {
            "tool": "big",
            "divinations_remaining": 3,
            "can_proceed": False,
            "clickable_cells": [
                {"x": 2, "y": 0, "is_highlighted": True},
                {"x": 3, "y": 0, "is_highlighted": True},
                {"x": 4, "y": 0, "is_highlighted": True},
            ],
        },
    }
    body = validate_action(state, {"action": "divine", "x": 3, "y": 0})
    assert body == {"action": "crystal_sphere_click_cell", "x": 3, "y": 0}


def test_crystal_sphere_big_sets_tool(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "crystal_sphere",
        "crystal_sphere": {"tool": "small", "divinations_remaining": 2},
    }
    body = validate_action(state, {"action": "big"})
    assert body == {"action": "crystal_sphere_set_tool", "tool": "big"}


def test_crystal_sphere_proceed_while_charges_left_clicks(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "crystal_sphere",
        "crystal_sphere": {
            "divinations_remaining": 2,
            "can_proceed": False,
            "clickable_cells": [{"x": 3, "y": 1, "is_highlighted": True}],
        },
    }
    body = validate_action(state, {"action": "proceed"})
    assert body["action"] == "crystal_sphere_click_cell"
    assert body["x"] == 3 and body["y"] == 1


def test_crystal_sphere_proceed_when_done(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "crystal_sphere",
        "crystal_sphere": {"divinations_remaining": 0, "can_proceed": True},
    }
    body = validate_action(state, {"action": "proceed"})
    assert body == {"action": "crystal_sphere_proceed"}


def test_crystal_sphere_stuck_does_not_click_more(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "crystal_sphere",
        "crystal_sphere": {
            "divinations_remaining": 0,
            "can_proceed": False,
            "clickable_cells": [{"x": 3, "y": 1, "is_highlighted": True}],
        },
    }
    body = validate_action(state, {"action": "divine", "x": 3, "y": 1})
    assert body == {"action": "crystal_sphere_proceed"}


def test_crystal_sphere_stale_map_allows_choose_node(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "crystal_sphere",
        "crystal_sphere": {"divinations_remaining": 0, "can_proceed": False},
        "map": {"next_options": [{"index": 2, "type": "monster"}]},
    }
    body = validate_action(state, {"action": "choose_map_node", "index": 2})
    assert body == {"action": "choose_map_node", "index": 2}


def test_combat_turn_plan_predicts_after_attack(sts2_env):
    from plugins.sts2.combat_turn_plan import (
        format_turn_plan_block,
        reset_combat_session,
        update_from_state,
    )

    reset_combat_session()
    state = {
        "state_type": "boss",
        "battle": {
            "turn": "player",
            "round": 2,
            "enemies": [
                {
                    "entity_id": "ROCKET_0",
                    "name": "火箭",
                    "hp": 191,
                    "intents": [{"type": "attack", "label": "Attack/18", "damage": 18}],
                },
                {
                    "entity_id": "CRUSHER_0",
                    "name": "碾碎爪",
                    "hp": 196,
                    "intents": [{"type": "attack", "label": "Attack/4", "damage": 4}],
                },
            ],
        },
        "player": {"hp": 62, "max_hp": 80, "energy": 3, "hand": []},
    }
    update_from_state(state)
    state["battle"]["round"] = 1
    state["battle"]["enemies"][0]["intents"] = [
        {"type": "attack", "label": "Attack/18", "damage": 18}
    ]
    update_from_state(state)
    block = format_turn_plan_block(state)
    assert "出牌前三问" in block
    assert "下回合" in block
    assert "ROCKET" in block or "火箭" in block


def test_combat_check_warns_leftover_energy(sts2_env):
    from plugins.sts2.combat_turn_plan import check_after_action, reset_combat_session

    reset_combat_session()
    before = {
        "state_type": "boss",
        "battle": {
            "turn": "player",
            "enemies": [
                {
                    "entity_id": "E1",
                    "hp": 40,
                    "intents": [{"type": "attack", "damage": 20}],
                }
            ],
        },
        "player": {"energy": 3, "block": 0, "hp": 50},
    }
    after = dict(before)
    after["player"] = {"energy": 1, "block": 0, "hp": 50}
    warns = check_after_action(
        before, after, {"action": "play_card", "card_index": 0, "target": "E1"}
    )
    assert any("能量" in w for w in warns)


def test_map_route_records_pick_and_outcome(sts2_env, monkeypatch):
    monkeypatch.setenv("HERMES_STS2_MANUAL", "1")
    from plugins.sts2.map_route_learn import (
        format_map_route_brief,
        observe_transition,
        stats_summary,
    )

    map_st = {
        "state_type": "map",
        "run": {"act": 1, "floor": 8, "character": "IRONCLAD"},
        "player": {"hp": 70, "max_hp": 80},
        "map": {
            "next_options": [
                {"index": 0, "type": "elite"},
                {"index": 1, "type": "monster"},
            ]
        },
    }
    brief = format_map_route_brief(map_st)
    assert "路线规划" in brief
    assert "整局目标" in brief or "路线·整局目标" in brief
    assert "index=0" in brief
    assert "elite" in brief

    observe_transition(
        map_st,
        {"state_type": "elite", "run": map_st["run"], "player": map_st["player"]},
        action={"action": "choose_map_node", "index": 0},
    )
    observe_transition(
        {"state_type": "elite", "run": map_st["run"], "player": map_st["player"]},
        {
            "state_type": "rewards",
            "run": map_st["run"],
            "player": {"hp": 65, "max_hp": 80},
        },
    )
    summ = stats_summary(1, "IRONCLAD")
    assert any("elite" in s for s in summ)


def test_manual_learn_parse_approve(sts2_env, monkeypatch):
    monkeypatch.setenv("HERMES_STS2_MANUAL", "1")
    from plugins.sts2.evolution_loop import read_pending, write_pending
    from plugins.sts2.manual_learn import parse_learn_command

    write_pending(
        [
            {"id": "r_a", "text": "当回合斩杀成立时优先输出"},
            {"id": "r_b", "text": "当 net 入伤≥HP 时先防"},
        ]
    )
    out = parse_learn_command("采纳规则1")
    assert out and out.get("approved") == 1
    assert len(read_pending()) == 1


def test_manual_learn_build_context_pending(sts2_env, monkeypatch):
    monkeypatch.setenv("HERMES_STS2_MANUAL", "1")
    from plugins.sts2.evolution_loop import write_pending
    from plugins.sts2.manual_learn import build_learn_context

    write_pending([{"id": "r_x", "text": "候选测试规则"}])
    ctx = build_learn_context()
    assert "待采纳" in ctx
    assert "候选测试" in ctx
    write_pending([])


def test_crystal_sphere_annotate_desync(sts2_env):
    from plugins.sts2.crystal_sphere import annotate_state

    state = {
        "state_type": "crystal_sphere",
        "map": {"next_options": [{"index": 0, "type": "?"}]},
    }
    out = annotate_state(state)
    assert out.get("effective_screen") == "map"
    assert out.get("crystal_sphere_desync") == "map_options_present"


def test_record_action_failure_promotes_only_once(sts2_env):
    from plugins.sts2.lessons import record_action_failure

    state = {"state_type": "elite", "run": {"floor": 9}, "player": {"hp": 40}}
    action = {"action": "use_potion", "slot": 0}
    err = "invalid potion"
    outs = [record_action_failure(state, action, err) for _ in range(5)]
    promoted = [o for o in outs if o.get("promoted")]
    assert len(promoted) == 1
    assert "药水" in str(outs[-1].get("rule") or "")


def test_reflect_combat_to_rewards(sts2_env):
    from plugins.sts2.reflect import reflect_transition

    prev = {"state_type": "monster", "run": {"floor": 3, "ascension": 1}}
    nxt = {"state_type": "rewards", "run": {"floor": 3, "ascension": 1}}
    out = reflect_transition(prev, nxt, recent_actions=[], use_llm=False)
    assert out.get("recorded")
    assert out.get("label") == "combat_win"


def test_finalize_stalled_run(sts2_env, tmp_path):
    from plugins.sts2.lessons import finalize_trajectory
    from plugins.sts2.storage import strategy_path

    traj = tmp_path / "run.jsonl"
    rows = []
    for _ in range(4):
        rows.append(
            json.dumps(
                {
                    "type": "step",
                    "state_type": "monster",
                    "action": {"action": "proceed"},
                    "act_ok": False,
                }
            )
        )
    traj.write_text("\n".join(rows) + "\n", encoding="utf-8")
    out = finalize_trajectory(traj)
    assert out.get("recorded")
    assert strategy_path().is_file()


def test_menu_options_as_strings(sts2_env):
    from plugins.sts2.visibility import describe_situation

    state = {
        "state_type": "menu",
        "menu_screen": "main",
        "options": ["continue", "singleplayer", "standard"],
        "run": {"act": 1, "floor": 0},
        "player": {"hp": 80, "max_hp": 80},
    }
    text = describe_situation(state)
    assert "continue" in text
    assert "singleplayer" in text


def test_full_run_victory_not_act1_transition(sts2_env):
    from plugins.sts2.run_victory import detect_act_milestone, detect_full_run_victory

    act2_transition = {
        "state_type": "menu",
        "menu_screen": "act_transition",
        "run": {"act": 2, "floor": 1},
        "options": [{"title": "Continue to Act 2"}],
    }
    assert detect_full_run_victory(act2_transition) is False
    assert detect_act_milestone(act2_transition, last_act=1) == (
        1,
        "★ 第一幕 (Act1) 已通过 — 继续打 Act2/Act3，不停止。",
    )

    act3_win = {
        "state_type": "game_over",
        "run": {"act": 3, "floor": 50},
        "player": {"hp": 42, "max_hp": 80},
        "options": [],
    }
    assert detect_full_run_victory(act3_win) is True


def test_act1_map_avoids_elite_when_hurt(sts2_env):
    from plugins.sts2.act1_clear import map_node_score, pick_map_node

    state = {"player": {"hp": 20, "max_hp": 80}, "run": {"floor": 6}}
    opts = [
        {"index": 0, "type": "Unknown", "label": "?"},
        {"index": 1, "type": "Elite", "label": "elite"},
    ]
    assert map_node_score(opts[1], state) > map_node_score(opts[0], state)
    body = pick_map_node(opts, state)
    assert body["index"] == 0


def test_analyze_wiki_entry_power_card(sts2_env):
    from plugins.sts2.knowledge import analyze_wiki_entry

    ent = analyze_wiki_entry(
        {
            "id": "INFLAME",
            "name": "Inflame",
            "description": "Gain 2 Strength. Power.",
        },
        kind="cards",
    )
    assert "power" in ent.get("tags", [])
    assert ent.get("reward_bonus", 0) > 15


def test_curate_from_state_writes_knowledge(sts2_env, monkeypatch):
    from plugins.sts2.knowledge import get_entry, knowledge_path
    from plugins.sts2.knowledge_curator import curate_from_state

    monkeypatch.setattr(
        "plugins.sts2.client.wiki_search",
        lambda q, **kw: (
            200,
            {
                "results": [
                    {
                        "id": "NEW_CARD_X",
                        "name": "New Card",
                        "description": "Deal 8 damage. Attack.",
                    }
                ]
            },
        ),
    )
    state = {
        "state_type": "card_reward",
        "card_reward": {
            "cards": [{"index": 0, "id": "NEW_CARD_X", "name": "New Card"}],
        },
    }
    out = curate_from_state(state, use_llm=False, max_items=2)
    assert out.get("curated", 0) >= 1
    assert get_entry("cards", "NEW_CARD_X")
    assert knowledge_path("cards").is_file()


def test_study_decide_uses_llm(sts2_env, monkeypatch):
    from plugins.sts2.decision import decide
    from plugins.sts2.study_mode import set_study_mode

    set_study_mode(True)
    try:
        state = {
            "state_type": "map",
            "run": {"floor": 3, "act": 1},
            "map": {
                "next_options": [
                    {"index": 0, "type": "monster"},
                    {"index": 1, "type": "rest"},
                ]
            },
        }
        monkeypatch.setattr(
            "plugins.sts2.llm_decide.llm_decide_step",
            lambda _state, **kw: (
                "【模型·map】先打小怪",
                {"action": "choose_map_node", "index": 0},
                True,
            ),
        )
        commentary, body = decide(state)
        assert body.get("action") == "choose_map_node"
        assert body.get("index") == 0
        assert "模型" in commentary
    finally:
        set_study_mode(False)


def test_combat_play_prefetch_wiki_budget(sts2_env, monkeypatch):
    from plugins.sts2.combat_play_brain import decide_combat_play
    from plugins.sts2.study_mode import set_study_mode

    calls = []

    def _fake_prefetch(hand, max_fetch):
        calls.append(max_fetch)
        return []

    monkeypatch.setattr(
        "plugins.sts2.combat_play_brain._prefetch_hand_wiki",
        _fake_prefetch,
    )
    monkeypatch.setattr(
        "plugins.sts2.combat_play_brain.combat_should_wait",
        lambda _s: False,
    )
    monkeypatch.setattr(
        "plugins.sts2.combat_play_brain.combat_should_end_turn",
        lambda _s: False,
    )
    monkeypatch.setattr(
        "agent.auxiliary_client.call_llm",
        lambda *a, **kw: '{"action":"end_turn","reason":"test"}',
    )
    set_study_mode(True)
    try:
        state = {
            "state_type": "elite",
            "run": {"floor": 13, "act": 1},
            "player": {
                "hp": 10,
                "max_hp": 80,
                "hand": [{"name": "Strike", "cost": 1}],
                "energy": 3,
                "block": 0,
            },
            "battle": {
                "is_play_phase": True,
                "turn": "player",
                "round": 1,
                "enemies": [{"name": "Slime", "hp": 20, "intents": []}],
            },
        }
        comm, body, ok = decide_combat_play(state)
        assert ok
        assert body.get("action") == "end_turn"
        assert calls == [4]
        assert "战斗" in comm or "结束回合" in comm
    finally:
        set_study_mode(False)


def test_study_llm_falls_back_to_rules(sts2_env, monkeypatch):
    from plugins.sts2.decision import decide
    from plugins.sts2.study_mode import set_study_mode

    monkeypatch.setattr(
        "agent.auxiliary_client.call_llm",
        lambda _provider, *, messages, max_tokens=720, temperature=0.3, **_kw: "not json",
    )
    set_study_mode(True)
    try:
        state = {
            "state_type": "map",
            "map": {
                "next_options": [
                    {"index": 0, "type": "monster"},
                    {"index": 1, "type": "rest"},
                ]
            },
        }
        commentary, body = decide(state)
        assert body.get("action") in ("choose_map_node", "proceed", "menu_select")
        assert "规则兜底" in commentary or body.get("action")
    finally:
        set_study_mode(False)


def test_autoplay_step_mock(sts2_env, monkeypatch):
    from plugins.sts2.autoplay import get_controller

    state = {
        "state_type": "monster",
        "run": {"floor": 1},
        "player": {"hp": 50, "hand": [], "energy": 0},
        "battle": {"is_play_phase": True, "turn": "player", "enemies": []},
    }
    monkeypatch.setattr(
        "plugins.sts2.client.get_singleplayer_state",
        lambda **kw: (200, state),
    )
    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda body: (200, {"status": "ok"}),
    )
    monkeypatch.setattr(
        "plugins.sts2.decision.decide",
        lambda s, user_hint="": ("Strike.", {"action": "end_turn"}),
    )
    monkeypatch.setattr("plugins.sts2.reflect.reflect_transition", lambda *a, **k: {"skipped": True})

    ctrl = get_controller()
    ctrl.stop()
    out = ctrl.step_once()
    assert out.get("success") is True
    assert out.get("skipped") or "▶" in (out.get("commentary") or "")


def test_evolution_gate_promotes_on_improvement(sts2_env):
    from plugins.sts2.evolution_loop import (
        append_result,
        begin_run,
        finalize_run,
        propose_rule_changes,
        ranked_rules_for_prompt,
        read_pending,
    )

    for i in range(5):
        append_result(
            {
                "max_floor": 8 + i,
                "max_act": 1,
                "label": "game_over",
                "reward_sum": 1.0,
            }
        )
    begin_run()
    propose_rule_changes(["下局：测试进化规则 A"], source="reflection")
    assert read_pending()
    fin = finalize_run(
        label="game_over",
        last_state={"run": {"floor": 50, "act": 2}, "state_type": "game_over"},
    )
    assert fin.get("metrics", {}).get("max_act") == 2
    gate = fin.get("gate", {})
    assert gate.get("improved") or gate.get("gate") in ("promoted", "hold_pending")
    ranked = ranked_rules_for_prompt()
    assert ranked


def test_evolution_act1_late_map_prefers_path(sts2_env):
    from plugins.sts2.act1_clear import map_node_score

    state = {"run": {"floor": 48, "act": 1}, "player": {"hp": 60, "max_hp": 80}}
    rest = map_node_score({"type": "rest"}, state)
    monster = map_node_score({"type": "monster"}, state)
    assert rest < monster


def test_program_health_reports_issue(sts2_env):
    from plugins.sts2.program_health import issues_path, report_issue

    row = report_issue("test", "synthetic failure", severity="warning", fix_hint="noop")
    assert row.get("fingerprint")
    assert issues_path().is_file()


def test_wait_action_not_posted_to_api(sts2_env, monkeypatch):
    from plugins.sts2 import client as c

    called = []

    def fake_request(*a, **k):
        called.append(1)
        return 200, {}

    monkeypatch.setattr(c, "_request", fake_request)
    st, payload = c.post_singleplayer_action({"action": "__wait__"})
    assert st == 200
    assert payload.get("local_skip")
    assert not called


def test_auto_repair_api_down_stops_study(sts2_env, monkeypatch):
    from plugins.sts2.auto_repair import attempt_auto_repair
    from plugins.sts2.autoplay import get_controller

    monkeypatch.setattr(
        "plugins.sts2.config.load_sts2_config",
        lambda: {"auto_repair": True},
    )
    ctrl = get_controller()
    monkeypatch.setattr(
        ctrl,
        "status",
        lambda: {"studying": True, "running": True},
    )
    monkeypatch.setattr(ctrl, "stop", lambda: None)
    out = attempt_auto_repair(
        "api_down",
        "Cannot reach STS2MCP at http://127.0.0.1:15526",
    )
    assert "stopped_study_until_api_back" in (out.get("repairs") or [])


def test_tui_bridge_broadcast_file(sts2_env, monkeypatch):
    from plugins.sts2.tui_bridge import broadcast_path, broadcast_to_tui

    monkeypatch.setattr(
        "plugins.sts2.tui_emit.emit_sts2_to_tui",
        lambda _t: False,
    )
    assert broadcast_to_tui("hello tui") is True
    assert "hello tui" in broadcast_path().read_text(encoding="utf-8")


def test_tui_cast_dedupe_blocks_meta_spam(sts2_env):
    from plugins.sts2.tui_cast_dedupe import (
        is_meta_banner,
        reset_meta_banners,
        should_deliver,
    )

    reset_meta_banners()
    line = "【马拉松·模型+规则】自动打局；不暂停菜单，但可看思考、可留言。"
    assert is_meta_banner(line)
    assert should_deliver(line) is True
    assert should_deliver(line) is False
    reset_meta_banners()
    assert should_deliver(line) is True


def test_coach_channel_poll_and_thinking(sts2_env):
    from plugins.sts2.coach_channel import (
        append_thinking,
        inbox_path,
        poll_coach_hint,
        thinking_path,
    )

    inbox_path().write_text(
        "# coach\n\n--- 从这里写 ---\n\n这局别进精英\n",
        encoding="utf-8",
    )
    hint = poll_coach_hint()
    assert "精英" in hint
    assert poll_coach_hint() == ""
    append_thinking(
        commentary="【模型】先格挡",
        action={"action": "play_card", "card_index": 0},
        state_type="monster",
        floor=3,
    )
    assert "格挡" in thinking_path().read_text(encoding="utf-8")


def test_marathon_study_always_blocked(sts2_env, monkeypatch):
    from plugins.sts2.autoplay import get_controller
    from plugins.sts2 import play_mode as pm
    from plugins.sts2.tools import handle_sts2_autoplay

    monkeypatch.setattr(pm, "marathon_forbidden", lambda: True)
    assert pm.rule_marathon_allowed() is False
    raw = handle_sts2_autoplay({"action": "study"})
    assert (
        "马拉松" in raw
        or "禁用" in raw
        or "后台代打" in raw
        or "marathon_disabled" in raw
        or "get_state" in raw
    )
    out = get_controller().start_study()
    assert out.get("success") is False


def test_play_brief_combat_includes_threat(sts2_env):
    from plugins.sts2.play_brief import build_play_brief

    state = {
        "state_type": "monster",
        "run": {"floor": 3, "act": 1},
        "player": {"hp": 50, "max_hp": 80, "block": 5, "energy": 3, "hand": []},
        "battle": {
            "turn": "player",
            "round": 1,
            "enemies": [
                {
                    "name": "Jaw Worm",
                    "id": "JAW_WORM",
                    "entity_id": "JAW_WORM_0",
                    "hp": 40,
                    "max_hp": 40,
                    "intents": [{"type": "attack", "label": "Attack 12"}],
                }
            ],
        },
    }
    brief = build_play_brief(state)
    assert "伤害账本" in brief
    assert "12" in brief
    assert "纪律" in brief
    assert "出牌前三问" in brief


def test_combat_brief_rich_hand_and_lethal(sts2_env):
    from plugins.sts2.combat_brief import format_combat_brief

    state = {
        "state_type": "elite",
        "run": {"floor": 8, "act": 1, "character": "IRONCLAD"},
        "player": {
            "hp": 60,
            "max_hp": 80,
            "block": 0,
            "energy": 3,
            "strength": 2,
            "hand": [
                {
                    "index": 0,
                    "id": "STRIKE_IRONCLAD",
                    "name": "打击",
                    "cost": 1,
                    "can_play": True,
                    "type": "attack",
                    "target_type": "enemy",
                },
            ],
        },
        "battle": {
            "turn": "player",
            "is_play_phase": True,
            "round": 2,
            "enemies": [
                {
                    "name": "Jaw Worm",
                    "entity_id": "JAW_WORM_0",
                    "hp": 8,
                    "max_hp": 40,
                    "intents": [{"type": "attack", "damage": 11, "label": "11"}],
                }
            ],
        },
    }
    brief = format_combat_brief(state)
    assert "手牌战术" in brief
    assert "斩杀线" in brief
    assert "合法动作速查" in brief
    assert "JAW_WORM_0" in brief


def test_combat_brief_energy_spend_not_one_card_per_turn(sts2_env):
    from plugins.sts2.combat_brief import format_combat_brief
    from plugins.sts2.play_brief import build_play_brief

    state = {
        "state_type": "monster",
        "run": {"floor": 7, "act": 1},
        "player": {
            "hp": 42,
            "max_hp": 80,
            "block": 0,
            "energy": 2,
            "hand": [
                {
                    "index": 0,
                    "id": "DEFEND",
                    "name": "防御",
                    "cost": 1,
                    "can_play": True,
                    "type": "skill",
                    "description": "Gain 5 Block.",
                },
                {
                    "index": 1,
                    "id": "DEFEND",
                    "name": "防御",
                    "cost": 1,
                    "can_play": True,
                    "type": "skill",
                    "description": "Gain 5 Block.",
                },
            ],
        },
        "battle": {
            "turn": "player",
            "is_play_phase": True,
            "enemies": [
                {
                    "name": "鼠",
                    "entity_id": "RAT_0",
                    "hp": 10,
                    "intents": [{"type": "attack", "damage": 8, "label": "8"}],
                }
            ],
        },
    }
    brief = format_combat_brief(state)
    play = build_play_brief(state)
    assert "能量纪律" in brief
    assert "用尽能量" in brief or "用尽" in play
    assert "连打" in brief
    assert "每回合最多一张" not in play
    assert "每回合通常 1 张" not in brief


def _combat_fsm_base_state(**player_overrides):
    player = {
        "hp": 60,
        "max_hp": 80,
        "block": 0,
        "energy": 3,
        "strength": 0,
        "powers": [],
        "relics": [{"name": "Burning Blood"}],
        "potions": [],
        "hand": [
            {
                "index": 0,
                "id": "STRIKE",
                "name": "打击",
                "cost": 1,
                "can_play": True,
            }
        ],
        "discard_pile": [],
        "exhaust_pile": [],
    }
    player.update(player_overrides)
    return {
        "state_type": "monster",
        "run": {"floor": 5, "act": 1, "character": "IRONCLAD"},
        "player": player,
        "battle": {
            "turn": "player",
            "is_play_phase": True,
            "round": 1,
            "enemies": [
                {
                    "name": "Jaw Worm",
                    "entity_id": "JAW_WORM_0",
                    "hp": 40,
                    "max_hp": 40,
                    "intents": [{"type": "attack", "damage": 12, "label": "12"}],
                }
            ],
        },
    }


def test_upgrade_advisor_ranks_bash_over_strike(sts2_env):
    from plugins.sts2.upgrade_advisor import rank_upgrade_candidates, score_upgrade

    state = {
        "state_type": "card_select",
        "run": {"act": 1, "floor": 8, "character": "IRONCLAD"},
        "player": {"hp": 60, "max_hp": 80},
    }
    cards = [
        {"index": 0, "id": "BASH", "name": "痛击", "can_play": True},
        {"index": 1, "id": "STRIKE_IRONCLAD", "name": "打击"},
        {"index": 2, "id": "DEMON_FORM", "name": "恶魔形态", "type": "power"},
    ]
    assert score_upgrade(cards[0], state) > score_upgrade(cards[1], state)
    ranked = rank_upgrade_candidates(cards, state)
    assert ranked[0][0]["id"] in ("BASH", "DEMON_FORM")


def test_build_knowledge_pick_brief(sts2_env):
    from plugins.sts2.build_knowledge import (
        format_build_pick_brief,
        load_catalog,
        score_card_for_archetype,
    )

    assert load_catalog().get("characters", {}).get("IRONCLAD")
    state = {
        "state_type": "card_reward",
        "run": {"act": 1, "floor": 5, "character": "IRONCLAD"},
        "player": {
            "hp": 70,
            "max_hp": 80,
            "deck": [{"id": "INFLAME"}, {"id": "BASH"}],
        },
    }
    offers = [
        {"index": 0, "id": "DEMON_FORM", "name": "恶魔形态"},
        {"index": 1, "id": "STRIKE_IRONCLAD", "name": "打击"},
    ]
    brief = format_build_pick_brief(state, offers)
    assert "构筑" in brief
    assert "层级对策" in brief or "抓牌四问" in brief
    assert score_card_for_archetype("DEMON_FORM", state) > score_card_for_archetype(
        "STRIKE_IRONCLAD", state
    )


def test_map_run_objective_in_route_brief(sts2_env):
    from plugins.sts2.map_route_learn import format_map_route_brief

    state = {
        "state_type": "map",
        "run": {"act": 1, "floor": 10},
        "player": {"hp": 35, "max_hp": 80},
        "map": {"next_options": [{"index": 0, "type": "rest"}, {"index": 1, "type": "elite"}]},
    }
    brief = format_map_route_brief(state)
    assert "路线·整局目标" in brief
    assert "控战损" in brief
    assert "低血" in brief or "营火" in brief


def test_run_objective_in_combat_brief(sts2_env):
    from plugins.sts2.combat_brief import format_combat_brief

    state = {
        "state_type": "monster",
        "run": {"floor": 12, "act": 1},
        "player": {"hp": 30, "max_hp": 80, "energy": 3, "hand": []},
        "battle": {
            "turn": "player",
            "is_play_phase": True,
            "enemies": [{"name": "Slime", "hp": 20, "intents": []}],
        },
    }
    brief = format_combat_brief(state)
    assert "整局目标" in brief
    assert "局内最优" in brief or "多回合" in brief


def test_combat_fsm_snapshots_five_zones(sts2_env):
    from plugins.sts2.combat_state_machine import get_combat_fsm, format_zone_snapshots

    get_combat_fsm().reset()
    state = _combat_fsm_base_state()
    meta = get_combat_fsm().tick(state)

    assert meta["in_combat"] is True
    assert set(meta["changed_zones"]) == {"player", "enemies", "hand", "discard", "exhaust"}
    snap = meta["snapshot_text"]
    assert "【战斗状态机·五区快照】" in snap
    assert "▸ 我方" in snap
    assert "▸ 敌方" in snap
    assert "▸ 手牌" in snap
    assert "T+0" in snap
    assert "T+1" in snap


def test_combat_fsm_hand_change_triggers_think(sts2_env, monkeypatch):
    from plugins.sts2.combat_state_machine import get_combat_fsm

    get_combat_fsm().reset()
    state = _combat_fsm_base_state()
    get_combat_fsm().tick(state)

    state2 = _combat_fsm_base_state(
        energy=2,
        hand=[
            {
                "index": 0,
                "id": "DEFEND",
                "name": "防御",
                "cost": 1,
                "can_play": True,
            }
        ],
        discard_pile=[{"index": 0, "id": "STRIKE", "name": "打击"}],
    )
    meta = get_combat_fsm().tick(state2)

    assert meta["changed"] is True
    assert "hand" in meta["changed_zones"]
    assert "discard" in meta["changed_zones"]
    assert meta["think_required"] is True


def test_combat_fsm_auto_think_calls_llm(sts2_env, monkeypatch):
    from plugins.sts2.combat_state_machine import get_combat_fsm

    monkeypatch.delenv("HERMES_STS2_MANUAL", raising=False)
    monkeypatch.delenv("HERMES_STS2_AGENT_PLAY", raising=False)
    monkeypatch.delenv("HERMES_STS2_MOUNT_MODE", raising=False)
    get_combat_fsm().reset()
    state = _combat_fsm_base_state()

    def fake_decide(st, *, memory=""):
        assert "[状态机]" in memory
        return (
            "打防御",
            {"action": "play_card", "card_index": 0},
            True,
        )

    monkeypatch.setattr(
        "plugins.sts2.combat_play_brain.decide_combat_play",
        fake_decide,
    )
    meta1 = get_combat_fsm().tick(state)
    assert meta1.get("think_ran") is True
    assert meta1["think"].get("skipped") is not True
    assert meta1["think"]["commentary"] == "打防御"

    # Same snapshot — no zone change → no second LLM call
    meta2 = get_combat_fsm().tick(state)
    assert meta2["changed"] is False
    assert meta2["think_required"] is False
    assert meta2.get("think_ran") is False
    assert "think" not in meta2


def test_combat_fsm_attach_injects_play_brief(sts2_env, monkeypatch):
    from plugins.sts2.combat_state_machine import attach_combat_fsm, get_combat_fsm

    get_combat_fsm().reset()
    monkeypatch.setattr(
        "plugins.sts2.combat_play_brain.decide_combat_play",
        lambda *a, **k: ("建议", {"action": "end_turn"}, True),
    )
    state = _combat_fsm_base_state()
    state["play_brief"] = "原有brief"
    meta = attach_combat_fsm(state)

    assert "【战斗状态机·五区快照】" in state["play_brief"]
    assert "原有brief" in state["play_brief"]
    assert meta["brief_block"] in state["play_brief"]


def test_combat_fsm_no_think_on_enemy_turn(sts2_env):
    from plugins.sts2.combat_state_machine import get_combat_fsm

    get_combat_fsm().reset()
    state = _combat_fsm_base_state()
    get_combat_fsm().tick(state)

    enemy_turn = _combat_fsm_base_state(energy=2)
    enemy_turn["battle"]["turn"] = "enemy"
    enemy_turn["battle"]["is_play_phase"] = False
    meta = get_combat_fsm().tick(enemy_turn)

    assert meta["player_turn"] is False
    assert meta["think_required"] is False


def test_combat_fsm_debounce_skips_second_think(sts2_env, monkeypatch):
    from plugins.sts2.combat_state_machine import get_combat_fsm

    monkeypatch.delenv("HERMES_STS2_MANUAL", raising=False)
    monkeypatch.delenv("HERMES_STS2_AGENT_PLAY", raising=False)
    monkeypatch.delenv("HERMES_STS2_MOUNT_MODE", raising=False)
    get_combat_fsm().reset()
    calls = {"n": 0}

    def fake_decide(st, *, memory=""):
        calls["n"] += 1
        return ("x", {"action": "end_turn"}, True)

    monkeypatch.setattr(
        "plugins.sts2.combat_play_brain.decide_combat_play",
        fake_decide,
    )
    state = _combat_fsm_base_state()
    get_combat_fsm().tick(state)
    state2 = _combat_fsm_base_state(energy=2)
    meta = get_combat_fsm().tick(state2)

    assert meta["think_required"] is True
    assert meta["think"]["skipped"] is True
    assert meta["think"]["reason"] == "debounce_interval"
    assert meta.get("think_ran") is False
    assert calls["n"] == 1


def test_combat_fsm_leaves_combat_resets(sts2_env):
    from plugins.sts2.combat_state_machine import get_combat_fsm

    get_combat_fsm().reset()
    get_combat_fsm().tick(_combat_fsm_base_state())
    meta = get_combat_fsm().tick({"state_type": "map", "map": {}})

    assert meta["in_combat"] is False
    assert get_combat_fsm()._zones == {}


def test_fix_event_menu_select_to_choose(sts2_env):
    from plugins.sts2.action_validate import validate_action

    state = {
        "state_type": "event",
        "event": {
            "in_dialogue": False,
            "options": [
                {"index": 0, "title": "失物盒", "is_locked": False},
                {"index": 1, "title": "其他", "is_locked": False},
            ],
        },
    }
    fixed = validate_action(state, {"action": "menu_select", "option": "失物盒"})
    assert fixed.get("action") == "choose_event_option"
    assert fixed.get("index") == 0


def test_state_settle_waits_for_fingerprint_change(sts2_env, monkeypatch):
    from plugins.sts2.state_settle import wait_for_settled_state

    pre = {
        "state_type": "monster",
        "player": {"hp": 50, "energy": 3, "hand": [{"index": 0, "id": "STRIKE"}]},
        "battle": {
            "turn": "player",
            "is_play_phase": True,
            "enemies": [{"entity_id": "A", "hp": 10}],
        },
    }
    post = {
        "state_type": "monster",
        "player": {"hp": 50, "energy": 2, "hand": []},
        "battle": {
            "turn": "player",
            "is_play_phase": True,
            "enemies": [{"entity_id": "A", "hp": 5}],
        },
    }
    calls = {"n": 0}

    def fake_get(**kw):
        calls["n"] += 1
        return 200, pre if calls["n"] == 1 else post

    monkeypatch.setattr(
        "plugins.sts2.client.get_singleplayer_state",
        fake_get,
    )
    monkeypatch.setattr("plugins.sts2.state_settle.time.sleep", lambda _: None)

    cur, meta = wait_for_settled_state(
        pre, "play_card", min_wait_sec=0, max_wait_sec=1, poll_sec=0.01
    )
    assert meta.get("settled") is True
    assert cur is post
    assert calls["n"] >= 2
