"""Choose STS2 actions (rules + auxiliary LLM)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import Any, Dict, Optional, Tuple

from plugins.sts2.config import load_sts2_config
from plugins.sts2.combat_brain import decide_combat
from plugins.sts2.lessons import should_avoid_elite_early
from plugins.sts2.notes import recall_block
from plugins.sts2.study_mode import is_study_mode
from plugins.sts2.visibility import describe_action, describe_situation

logger = logging.getLogger(__name__)

_COMBAT_STATES = frozenset({"monster", "elite", "boss"})

# -- Hot-reload support ----------------------------------------------------
_DECISION_FILE = __file__  # known at module load time
_DECISION_MTIME = 0.0


def _check_reload() -> None:
    """Reload this module from disk if the file changed since last check."""
    global _DECISION_MTIME
    try:
        current_mtime = os.path.getmtime(_DECISION_FILE)
    except (OSError, TypeError):
        return
    if current_mtime > _DECISION_MTIME:
        _DECISION_MTIME = current_mtime
        # Reload ourself in-place
        import importlib
        modname = __name__
        if modname in sys.modules:
            importlib.reload(sys.modules[modname])
        _DECISION_MTIME = os.path.getmtime(_DECISION_FILE)


# -- Card evaluation weights (Ironclad defaults) --------------------------
_CARD_PRIORITY = {
    # Power cards: permanent scaling
    "INFLAME": 100,         # Burning: 2 strength permanent
    "DEMON_FORM": 95,       # Demon Form: 3 strength/turn
    "SPOT_WEAKNESS": 90,    # Spot Weakness: +3 strength/turn
    "FEEL_NO_PAIN": 80,     # Feel No Pain: block on exhaust
    "DARK_EMBRACE": 80,     # Dark Embrace: draw on exhaust
    "CORRUPTION": 85,       # Corruption: skills free + exhaust
    "BATTLE_TRANCE": 85,    # Battle Trance: draw cards
    "COMBUSTION": 75,       # Combustion: AOE + self-damage
    "RUPTURE": 70,          # Rupture: strength on self-damage
    "BRUTALITY": 70,        # Brutality: draw 1 + self-damage
    "BARRICADE": 75,        # Barricade: block carries over
    "ENTRENCH": 70,         # Entrench: double block
    "METALLICIZE": 60,      # Metallicize: block each turn
    "EVOLVE": 65,           # Evolve: draw on status
    "FIRE_BREATHING": 60,   # Fire Breathing: damage on status draw
    # Uncommon attack tools
    "BREAKTHROUGH": 65,     # Breakthrough: AOE 9 damage
    "WHIRLWIND": 70,        # Whirlwind: AOE scaling
    "UPON_A_BLADE": 65,     # Upon a Blade: draw 2 attacks
    "POMMEL_STRIKE": 60,    # Pommel Strike: damage + draw
    "SEVER_SOUL": 65,       # Sever Soul: high damage
    "BLOOD_FOR_BLOOD": 55,  # Blood for Blood: cheap after damage
    "HEMOKINESIS": 55,      # Hemokinesis: self-damage high strike
    "CARNIVORE": 45,        # Carnivore: heal
    # Common attack tools
    "SETUP_STRIKE": 50,     # Setup Strike: 7 damage + 2 strength
    "BASH": 45,             # Bash: vulnerable
    "ANGER": 60,            # Anger: 0-cost copy on use
    "CLASH": 40,            # Clash: 3-cost high damage
    "TREMBLE": 40,          # Tremble: vulnerable (exhaust)
    "TWIN_STRIKE": 50,      # Twin Strike: hit twice
    "WILDSTRIKE": 35,       # Wild Strike: gives wound
    "CLEAVE": 45,           # Cleave: AOE
    "HEADBUTT": 50,         # Headbutt: put card on draw pile
    "IRON_WAVE": 40,        # Iron Wave: damage + block
    "THUNDERCLAP": 50,      # Thunderclap: AOE + vulnerable
    "RAMPAGE": 45,          # Rampage: escalating damage
    "SHRUG_OFF": 55,        # Shrug It Off: block + draw
    "TRUE_GRIT": 50,        # True Grit: block + exhaust
    "GHOSTLY_ARMOR": 40,    # Ghostly Armor: block
    "POWER_THROUGH": 50,    # Power Through: block + wound
    "ARMAMENTS": 60,        # Armaments: upgrade cards
    "FLAME_BARRIER": 55,    # Flame Barrier: block + damage attacker
    "DISARM": 55,           # Disarm: reduce enemy strength
    "SHOCKWAVE": 60,        # Shockwave: AOE vulnerable + weak
    "UPPERCUT": 55,         # Uppercut: vulnerable + weak
    "INTIMIDATE": 40,       # Intimidate: weak
    "BLOOD_WALL": 35,       # Blood Wall: HP for 16 block
    # Strikes/defends
    "STRIKE_IRONCLAD": 10,
    "DEFEND_IRONCLAD": 10,
}


def _knowledge_reward_adjustment(card_id: str) -> float:
    try:
        from plugins.sts2.knowledge import card_reward_bonus

        return card_reward_bonus(str(card_id))
    except Exception:
        return 0.0


def _pick_best_card(cards: list[dict]) -> int | None:
    """Return index of best card for Ironclad, or None to skip."""
    best_idx = None
    best_score = -999
    for c in cards:
        idx = c.get("index", -1)
        rid = c.get("id", "")
        score = _CARD_PRIORITY.get(rid, 15) + _knowledge_reward_adjustment(rid)
        ctype = str(c.get("type", "")).lower()
        if ctype == "curse" or "curse" in str(c.get("id", "")).lower():
            score -= 80
        if ctype == "attack":
            score += 8
        name = str(c.get("name", "")).lower()
        if "strike" in name or "打击" in name:
            score += 5
        rarity = str(c.get("rarity", "")).lower()
        if rarity == "uncommon":
            score += 5
        elif rarity == "rare":
            score += 10
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


def _menu_character_action(opts: list) -> dict | None:
    """Pick unlocked character from config (``sts2.character`` / ``STS2_CHARACTER``)."""
    from plugins.sts2.character_choice import pick_character_menu_action

    return pick_character_menu_action(opts)


def _hp_ratio(state: dict | None) -> float:
    if not state:
        return 1.0
    player = state.get("player") or {}
    try:
        hp = int(player.get("hp", player.get("current_hp", 1)))
        max_hp = int(player.get("max_hp", hp) or hp or 1)
    except (TypeError, ValueError):
        return 1.0
    return hp / max_hp if max_hp > 0 else 1.0


def _pick_map_node(opts: list, state: dict | None = None) -> dict:
    """Map routing — Act1 通关导向 (see act1_clear)."""
    from plugins.sts2.act1_clear import pick_map_node

    return pick_map_node(opts, state)


def _safe_fallback(state: dict) -> tuple[str, dict]:
    """Never default to end_turn outside combat."""
    st = str(state.get("state_type") or "")
    ruled = _rule_action(state)
    if ruled:
        return _plan_commentary(state, ruled), ruled
    if st in _COMBAT_STATES:
        body = _coerce_action(state, decide_combat(state))
        return _plan_commentary(state, body), body
    from plugins.sts2.autonomy import autopilot_until_victory

    if st == "map" and not is_study_mode() and not autopilot_until_victory():
        return "Map unclear; pausing for user.", {"action": "__pause__"}
    if st == "map":
        opts = (state.get("map") or {}).get("next_options") or state.get("next_options") or []
        if opts:
            body = _pick_map_node(opts, state)
            return _plan_commentary(state, body), body
    return f"Fallback proceed at {st}.", {"action": "proceed"}


def _coerce_action(state: dict, body: dict) -> dict:
    """Rewrite illegal end_turn on non-combat screens."""
    action = str(body.get("action") or "").strip()
    st = str(state.get("state_type") or "")
    if action == "end_turn" and st not in _COMBAT_STATES:
        _, fixed = _safe_fallback(state)
        return fixed
    if action == "end_turn" and st in _COMBAT_STATES:
        from plugins.sts2.combat_brain import combat_should_wait

        if combat_should_wait(state):
            return {"action": "__wait__"}
    if action == "proceed" and st in _COMBAT_STATES:
        return {"action": "__wait__"}
    if action in ("skip_rest_option", "skip_rest", "leave_rest") and st == "rest_site":
        from plugins.sts2.action_validate import _fix_rest_site

        return _fix_rest_site(state, body)
    return body


def _rule_action(state: dict) -> dict | None:
    st = str(state.get("state_type") or "")

    # -- Menu navigation --
    if st == "menu":
        from plugins.sts2.run_flow import next_menu_action
        from plugins.sts2.safe_parse import normalize_options, option_enabled, option_label

        quick = next_menu_action(state)
        if quick:
            return quick
        opts = normalize_options(state.get("options") or [])
        screen = str(state.get("menu_screen") or "").lower()

        def _opt_name(o: dict) -> str:
            return option_label(o)

        def _enabled(o: dict) -> bool:
            return option_enabled(o)

        # Popups / tutorial — don't get stuck before floor 1
        if screen in ("tutorial_prompt", "popup", "ftue"):
            for key in ("ignore", "close", "continue", "ok", "no", "back"):
                for o in opts:
                    if _enabled(o) and _opt_name(o).lower() == key:
                        return {"action": "menu_select", "option": _opt_name(o)}
        if screen == "tutorial_prompt":
            return {"action": "menu_select", "option": "no"}

        if screen in ("timeline", "intro", "credits", "cutscene"):
            for key in ("advance", "continue", "skip", "proceed"):
                if key in [_opt_name(o).lower() for o in opts if _enabled(o)]:
                    for o in opts:
                        if _enabled(o) and _opt_name(o).lower() == key:
                            return {"action": "menu_select", "option": _opt_name(o)}

        opt_names = [_opt_name(o).lower() for o in opts if _enabled(o)]

        if "continue" in opt_names:
            return {"action": "menu_select", "option": "continue"}
        if "singleplayer" in opt_names:
            return {"action": "menu_select", "option": "singleplayer"}
        if "standard" in opt_names:
            return {"action": "menu_select", "option": "standard"}
        picked = _menu_character_action(opts)
        if picked:
            return picked
        if "embark" in opt_names:
            return {"action": "menu_select", "option": "embark"}
        if "confirm" in opt_names:
            return {"action": "menu_select", "option": "confirm"}
        if "no" in opt_names and "yes" in opt_names:
            return {"action": "menu_select", "option": "no"}
        for o in opts:
            if _enabled(o):
                name = _opt_name(o)
                if name:
                    return {"action": "menu_select", "option": name}
        return None

    # -- Card rewards --
    if st == "card_reward":
        from plugins.sts2.reward_cards import offer_reward_cards

        cards = offer_reward_cards(state)
        if not cards:
            from plugins.sts2.card_pick_brain import (
                card_reward_can_skip,
                card_reward_should_skip,
            )

            if card_reward_can_skip(state) and card_reward_should_skip(state, []):
                return {"action": "proceed"}
            return {"action": "select_card_reward", "card_index": 0}
        idx = _pick_best_card(cards)
        if idx is not None:
            return {"action": "select_card_reward", "card_index": idx}
        return {"action": "select_card_reward", "card_index": cards[0].get("index", 0)}

    # -- Events (Neow, etc.) --
    if st == "event":
        ev = state.get("event") or {}
        opts = [o for o in (ev.get("options") or []) if isinstance(o, dict)]
        pickable = [o for o in opts if not o.get("is_locked")]
        if ev.get("in_dialogue"):
            # API may keep in_dialogue after hitbox gone — prefer real options when present.
            if pickable:
                for o in pickable:
                    if not o.get("is_proceed", False):
                        return {
                            "action": "choose_event_option",
                            "index": o.get("index", 0),
                        }
                if len(pickable) == 1:
                    return {
                        "action": "choose_event_option",
                        "index": pickable[0].get("index", 0),
                    }
            return {"action": "advance_dialogue"}
        opts = pickable
        # Neow / Act1: skip heavy draft unless it's the only choice
        for o in opts:
            if o.get("is_locked"):
                continue
            title = str(o.get("title", "")).lower()
            if "draft" in title and len([x for x in opts if not x.get("is_locked")]) > 1:
                continue
            if not o.get("is_proceed", False):
                return {"action": "choose_event_option", "index": o.get("index", 0)}
        for o in opts:
            if not o.get("is_locked", False):
                return {"action": "choose_event_option", "index": o.get("index", 0)}
        return {"action": "proceed"}

    if st == "rewards":
        from plugins.sts2.rewards_screen import decide_rewards_screen

        return decide_rewards_screen(state)

    if st == "bundle_select":
        from plugins.sts2.bundle_select_brain import decide_bundle_select

        return decide_bundle_select(state)

    if st == "crystal_sphere":
        from plugins.sts2.crystal_sphere import decide_crystal_sphere

        return decide_crystal_sphere(state)

    # -- Combat hand selection (武装升级 / 生存者弃牌等) --
    if st == "hand_select":
        from plugins.sts2.hand_select_brain import decide_hand_select

        return decide_hand_select(state)

    # -- Card selection (upgrade / rest site upgrade / etc) --
    if st == "card_select":
        from plugins.sts2.reward_cards import offer_reward_cards

        cs = state.get("card_select") or {}
        screen_type = str(cs.get("screen_type", "")).lower()
        cards = offer_reward_cards(state)
        if cs.get("preview_showing", False):
            if cs.get("can_confirm", False):
                return {"action": "confirm_selection"}
            # preview_showing but can_confirm=False → need to pick a card first
            if cards:
                idx = _pick_best_card(cards)
                if idx is not None:
                    return {"action": "select_card", "index": idx}
            return {"action": "__wait__"}
        # Pick best card to upgrade or leave
        if cards:
            idx = _pick_best_card(cards)
            if idx is not None:
                return {"action": "select_card", "index": idx}
        return {"action": "proceed"}

    # -- Rest site --
    if st == "rest_site":
        rs = state.get("rest_site") or {}
        opts = rs.get("options") or []
        enabled = [o for o in opts if o.get("is_enabled", True)]
        if not enabled and rs.get("can_proceed", True):
            return {"action": "proceed"}
        ratio = _hp_ratio(state)
        if ratio < 0.72:
            for o in enabled:
                oid = str(o.get("id", o.get("name", ""))).lower()
                if "rest" in oid or "heal" in str(o.get("description", "")).lower():
                    return {"action": "choose_rest_option", "index": o.get("index", 0)}
        for o in enabled:
            oid = str(o.get("id", o.get("name", ""))).lower()
            if "smith" in oid or "upgrade" in oid:
                return {"action": "choose_rest_option", "index": o.get("index", 0)}
        for o in enabled:
            return {"action": "choose_rest_option", "index": o.get("index", 0)}
        return {"action": "proceed"}

    # -- Treasure: claim chest loot (never proceed first) --
    if st in ("treasure", "fake_merchant"):
        from plugins.sts2.treasure_rewards import decide_treasure_action

        return decide_treasure_action(state)

    if st == "shop":
        from plugins.sts2.safe_parse import normalize_options, option_enabled, option_label

        opts = normalize_options(state.get("options") or [])
        names = [option_label(o).lower() for o in opts if option_enabled(o)]
        if not names:
            return {"action": "proceed"}
        for prefer in ("leave", "continue", "proceed", "exit"):
            if prefer in names:
                for o in opts:
                    if option_enabled(o) and option_label(o).lower() == prefer:
                        return {"action": "menu_select", "option": option_label(o)}
        return {"action": "__wait__"}

    # -- Map --
    if st == "map":
        opts = state.get("map", {}).get("next_options") or state.get("next_options") or []
        if len(opts) == 1:
            return {"action": "choose_map_node", "index": opts[0].get("index", 0)}
        return _pick_map_node(opts, state)

    if st == "game_over":
        from plugins.sts2.run_flow import next_menu_action

        act = next_menu_action(state)
        return act or {"action": "menu_select", "option": "main_menu"}

    if st == "relic_select":
        relics = (state.get("relic_select") or {}).get("relics") or []
        if relics:
            best_i = relics[0].get("index", 0)
            best_s = -1
            for r in relics:
                blob = (
                    str(r.get("name", ""))
                    + str(r.get("description", ""))
                    + str(r.get("id", ""))
                ).lower()
                score = 0
                for kw, pts in (
                    ("energy", 30),
                    ("strength", 25),
                    ("dexterity", 20),
                    ("vulnerable", 15),
                    ("block", 12),
                    ("heal", 18),
                ):
                    if kw in blob:
                        score += pts
                if score > best_s:
                    best_s = score
                    best_i = r.get("index", 0)
            return {"action": "select_relic", "index": best_i}

    return None


def _needs_user_ask(state: dict) -> str | None:
    from plugins.sts2.autonomy import autopilot_until_victory

    if autopilot_until_victory() or is_study_mode():
        return None
    cfg = load_sts2_config()
    ask_on = {str(x) for x in (cfg.get("ask_user_on") or [])}
    st = str(state.get("state_type") or "")
    if st in ask_on:
        return (
            f"Decision needed at state_type={st}. "
            "Describe options from state and ask the user what to pick."
        )
    if st == "card_reward" and "card_reward" in ask_on:
        return (
            f"Decision needed at state_type={st}. "
            "Describe options from state and ask the user what to pick."
        )
    if st == "event" and "event" in ask_on:
        return (
            f"Decision needed at state_type={st}. "
            "Describe options from state and ask the user what to pick."
        )
    return None


def _parse_llm_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


_last_known_mtime = 0.0

def _ensure_fresh() -> None:
    """If decision.py changed on disk, re-import the module."""
    global _last_known_mtime
    try:
        mtime = os.path.getmtime(_DECISION_FILE)
    except (OSError, TypeError):
        return
    if mtime > _last_known_mtime:
        _last_known_mtime = mtime
        import importlib
        mod = sys.modules.get(__name__)
        if mod is not None:
            importlib.reload(mod)


def decide(
    state: dict,
    *,
    user_hint: str = "",
    recent_actions: Optional[list] = None,
) -> tuple[str, dict]:
    """Return (commentary, act_body)."""
    _ensure_fresh()
    # Always dispatch through sys.modules so autoplay's indirect import picks up changes
    return sys.modules[__name__]._decide_impl(
        state, user_hint=user_hint, recent_actions=recent_actions
    )


def _plan_commentary(state: dict, body: dict) -> str:
    """Pre-action commentary: full board + planned move."""
    return f"{describe_situation(state)}\n▶ {describe_action(state, body)}"


def _decide_impl(
    state: dict,
    *,
    user_hint: str = "",
    recent_actions: Optional[list] = None,
) -> tuple[str, dict]:
    """Core decide logic (called via indirection for hot-reload)."""
    cfg = load_sts2_config()
    from plugins.sts2.play_mode import use_llm_decision

    study = is_study_mode()
    use_llm = use_llm_decision()
    mem_prefix = ""
    if use_llm or cfg.get("apply_memory_each_step", True):
        try:
            from plugins.sts2.memory_bus import memory_prefix_for_commentary

            mem_prefix = memory_prefix_for_commentary()
        except Exception:
            mem_prefix = ""

    st = str(state.get("state_type") or "")

    # 武装/生存者选牌：禁止走战斗 LLM（会误发 play_card）
    if st == "hand_select":
        from plugins.sts2.hand_select_brain import decide_hand_select, hand_select_commentary

        body = decide_hand_select(state)
        comm = hand_select_commentary(state, body)
        sit = describe_situation(state)
        return (mem_prefix + f"【思路·选牌】\n{comm}\n{sit}").strip(), body

    if st == "bundle_select":
        from plugins.sts2.bundle_select_brain import (
            bundle_select_commentary,
            decide_bundle_select,
        )

        body = decide_bundle_select(state)
        comm = bundle_select_commentary(state, body)
        sit = describe_situation(state)
        return (mem_prefix + f"【思路·开局】\n{comm}\n{sit}").strip(), body

    if st == "rewards":
        if use_llm and cfg.get("study_use_llm", True):
            from plugins.sts2.llm_decide import llm_decide_step

            comm, body, ok = llm_decide_step(state, memory=mem_prefix)
            if ok and body:
                sit = describe_situation(state)
                return (mem_prefix + f"【思路·战后奖励】\n{comm}\n{sit}").strip(), body
        from plugins.sts2.rewards_screen import (
            decide_rewards_screen,
            format_rewards_commentary,
        )

        body = decide_rewards_screen(state)
        comm = format_rewards_commentary(state, body)
        sit = describe_situation(state)
        return (mem_prefix + f"【战后奖励·规则】\n{comm}\n{sit}").strip(), body

    if st in ("treasure", "fake_merchant"):
        from plugins.sts2.treasure_rewards import decide_treasure_action, format_treasure_offers

        body = decide_treasure_action(state)
        comm = f"【宝箱】先拿奖励再离开\n{format_treasure_offers(state)}"
        sit = describe_situation(state)
        return (mem_prefix + f"【思路·宝箱】\n{comm}\n▶ {describe_action(state, body)}\n{sit}").strip(), body

    # Combat: wiki + lessons + LLM (not rule scorer)
    if use_llm and st in _COMBAT_STATES:
        from plugins.sts2.combat_play_brain import decide_combat_play

        comm, body, ok = decide_combat_play(state, memory=mem_prefix)
        if ok and body:
            sit = describe_situation(state)
            return (mem_prefix + f"【思路·战斗】\n{comm}\n{sit}").strip(), body

    # Card reward: deck-building "思路" (LLM + skip) — not dumb priority list
    if use_llm and st == "card_reward":
        from plugins.sts2.card_pick_brain import decide_card_reward

        comm, body, ok = decide_card_reward(state, memory=mem_prefix)
        if ok and body:
            sit = describe_situation(state)
            return (mem_prefix + f"【思路·选卡】\n{comm}\n{sit}").strip(), body

    # Campfire smith / upgrade: handled by _rule_action below (preview_showing + can_confirm)
    # (study path removed)
    # Relic / gold rewards: rules only when marathon explicitly allows rule fallback
    _RULES_FIRST = frozenset({"relic_select", "relic_select_boss", "rewards"})
    if study and st in _RULES_FIRST and cfg.get("study_rules_fallback", False):
        ruled = _rule_action(state)
        if ruled:
            commentary = (mem_prefix + _plan_commentary(state, ruled)).strip()
            return (mem_prefix + f"【规则·奖】\n{commentary}").strip(), ruled

    # Menu / game_over: deterministic (fast, reliable)
    if st in ("menu", "game_over"):
        ruled = _rule_action(state)
        if ruled:
            commentary = (mem_prefix + _plan_commentary(state, ruled)).strip()
            return commentary, ruled

    # LLM for map/event/etc. (combat uses combat_play_brain above)
    if use_llm and cfg.get("study_use_llm", True):
        from plugins.sts2.llm_decide import llm_decide_step

        use_llm = st not in ("menu", "game_over") and st not in _COMBAT_STATES
        if st in ("hand_select", "bundle_select"):
            use_llm = False
        if st == "hand_select" and not cfg.get("study_llm_combat", True):
            use_llm = False
        if use_llm:
            comm, body, ok = llm_decide_step(
                state, user_hint=user_hint, memory=mem_prefix
            )
            if ok and body:
                tag = "模型"
                sit = describe_situation(state)
                return (
                    mem_prefix + f"【{tag}·{st}】\n{comm}\n{sit}".strip(),
                    body,
                )

    skip_rule_fallback = use_llm and not cfg.get("study_rules_fallback", False)
    if not skip_rule_fallback:
        ruled = _rule_action(state)
        if ruled:
            commentary = (mem_prefix + _plan_commentary(state, ruled)).strip()
            tag = "规则兜底" if study else ""
            prefix = f"【{tag}】\n" if tag else ""
            return (mem_prefix + prefix + commentary).strip(), ruled

    if not study and not use_llm:
        ask = _needs_user_ask(state)
        if ask and cfg.get("pause_on_ask", True):
            return ask, {"action": "__pause__"}

    if st in _COMBAT_STATES:
        if use_llm:
            comm, body = _safe_fallback(state)
            return (mem_prefix + f"【战斗·兜底】\n{comm}").strip(), body
        body = decide_combat(state, apply_lessons=True)
        coerced = _coerce_action(state, body)
        line = _plan_commentary(state, coerced)
        return (mem_prefix + f"【战斗】\n{line}").strip(), coerced

    # Per-turn LLM autopilot disabled by default (causes parse failures + illegal acts).
    import os

    llm_ok = (
        cfg.get("autoplay_use_llm", False)
        and os.environ.get("STS2_ALLOW_LLM_AUTOPILOT", "").strip() == "1"
        and not study
    )
    if not llm_ok:
        comm, body = _safe_fallback(state)
        return (mem_prefix + comm).strip(), body

    recall = recall_block()
    state_json = json.dumps(state, ensure_ascii=False)[:12000]
    prompt = (
        "You play Slay the Spire 2 via API. Respond with ONLY JSON:\n"
        '{"commentary":"2-4 sentences for the player","action":"...", ...params}\n'
        "Valid actions include play_card, end_turn, choose_map_node, menu_select, "
        "claim_reward, select_card_reward, choose_event_option, proceed, select_card, confirm_selection, cancel_selection, use_potion, etc. "
        "Use indices from the state only.\n"
    )
    if recall:
        prompt += f"\nMemory:\n{recall[:3000]}\n"
    if user_hint:
        prompt += f"\nUser said: {user_hint}\n"
    prompt += f"\nState:\n{state_json}"

    try:
        from agent.auxiliary_client import call_llm

        from plugins.sts2.llm_util import sts2_call_llm

        raw = sts2_call_llm(
            [
                {"role": "system", "content": "STS2 autopilot. JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.2,
        )
    except Exception as exc:
        logger.debug("sts2 decide LLM failed: %s", exc)
        raw = ""

    parsed = _parse_llm_json(raw or "")
    if not parsed:
        return _safe_fallback(state)

    commentary = str(parsed.pop("commentary", "") or "Continuing.")
    action = str(parsed.get("action") or "").strip()
    if not action or action == "__pause__":
        return _safe_fallback(state)
    body = _coerce_action(state, dict(parsed, action=action))
    return commentary, body
