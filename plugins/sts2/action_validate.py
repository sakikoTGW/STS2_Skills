"""Validate/fix actions against live state before POST (fewer illegal clicks)."""
from __future__ import annotations
from typing import Any, Dict, Optional
_COMBAT = frozenset({"monster", "elite", "boss", "hand_select"})


def _combat_play_fallback(state: dict) -> dict:
    """When LLM asks proceed/end_turn but cards+energy remain, play instead of wasting."""
    from plugins.sts2.combat_brain import combat_should_wait

    if combat_should_wait(state):
        return {"action": "__wait__"}
    try:
        from plugins.sts2.combat_scorer import decide_combat_scored

        body = decide_combat_scored(state)
        if body.get("action") not in ("end_turn", "__wait__"):
            return body
    except Exception:
        pass
    from plugins.sts2.combat_brain import decide_combat

    return decide_combat(state)


def validate_action(state: dict, body: dict) -> dict:
    """Return a legal action for this state (may differ from input)."""
    if not state or not body:
        return body or {"action": "proceed"}
    result = _validate_action_inner(state, body)
    try:
        from plugins.sts2.act1_policy import coerce_act1_action

        coerced, changed, _ = coerce_act1_action(state, result)
        if changed:
            return coerced
    except Exception:
        pass
    return result


def _validate_action_inner(state: dict, body: dict) -> dict:
    if not state or not body:
        return body or {"action": "proceed"}
    action = str(body.get("action") or "").strip()
    st = str(state.get("state_type") or "")
    if st == "crystal_sphere":
        from plugins.sts2.crystal_sphere import normalize_crystal_action

        return normalize_crystal_action(state, body)
    from plugins.sts2.treasure_rewards import is_treasure_context
    if is_treasure_context(state):
        act_low = action.lower()
        if act_low in ("claim_reward", "select_relic", "relic_select", "take_relic"):
            body = dict(body)
            from plugins.sts2.treasure_rewards import treasure_claim_body
            try:
                ix = int(body.get("index", body.get("relic_index", 0)))
            except (TypeError, ValueError):
                ix = 0
            body = treasure_claim_body(state, ix)
            action = str(body.get("action") or "")
        elif act_low == "proceed" and st in ("treasure", "fake_merchant"):
            from plugins.sts2.treasure_rewards import decide_treasure_action
            fixed = decide_treasure_action(state)
            if fixed.get("action") != "proceed":
                return fixed
    if st == "hand_select":
        from plugins.sts2.hand_select_brain import decide_hand_select
        if action in ("play_card", "use_potion"):
            return decide_hand_select(state)
        if action in ("end_turn", "proceed"):
            hs = state.get("hand_select") or {}
            if hs.get("can_confirm"):
                return {"action": "combat_confirm_selection"}
            return decide_hand_select(state)
        if action in ("combat_select_card", "combat_confirm_selection"):
            return body
    if st == "bundle_select":
        from plugins.sts2.bundle_select_brain import decide_bundle_select
        if action in ("proceed", "play_card", "end_turn"):
            return decide_bundle_select(state)
    if st in ("treasure", "fake_merchant"):
        # Treasure room: don't override user's action unless it's proceed
        # (which is handled above). Just pass through.
        return body
    if action == "end_turn":
        if st not in _COMBAT:
            return _fallback(state)
        from plugins.sts2.combat_brain import combat_should_end_turn, combat_should_wait

        if combat_should_wait(state):
            return {"action": "__wait__"}
        try:
            from plugins.sts2.manual_mode import manual_mode_enabled

            if manual_mode_enabled():
                return body
        except Exception:
            pass
        if not combat_should_end_turn(state):
            return _combat_play_fallback(state)
        return body
    if action == "proceed":
        if st == "bundle_select":
            from plugins.sts2.bundle_select_brain import decide_bundle_select
            return decide_bundle_select(state)
        if st in ("treasure", "fake_merchant"):
            # Always allow proceed through treasure — the chest may have
            # already been opened (gold received) but the game API still
            # shows the relic as unclaimed. Repeated claim_treasure_relic
            # calls just return "Rewards screen is not open".
            return body
        if st in _COMBAT:
            from plugins.sts2.combat_brain import (
                combat_should_end_turn,
                combat_should_wait,
            )

            if combat_should_wait(state):
                return {"action": "__wait__"}
            try:
                from plugins.sts2.manual_mode import manual_mode_enabled

                if manual_mode_enabled():
                    return {"action": "__pause__"}
            except Exception:
                pass
            if combat_should_end_turn(state):
                return {"action": "end_turn"}
            return _combat_play_fallback(state)
        if st == "card_reward":
            from plugins.sts2.card_pick_brain import (
                card_reward_can_skip,
                card_reward_should_skip,
            )
            from plugins.sts2.reward_cards import offer_reward_cards
            offers = offer_reward_cards(state)
            if card_reward_can_skip(state) and card_reward_should_skip(
                state, offers
            ):
                return body
            return _fix_card_reward(
                state, {"action": "select_card_reward", "card_index": 0}
            )
        if st == "card_select":
            from plugins.sts2.card_pick_brain import card_reward_can_skip
            from plugins.sts2.reward_cards import offer_reward_cards
            cs = state.get("card_select") or {}
            if cs.get("preview_showing"):
                return {"action": "confirm_selection"}
            if offer_reward_cards(state) and not card_reward_can_skip(state):
                return _fix_select_card(state, {"action": "select_card", "index": 0})
        if st == "rewards":
            from plugins.sts2.rewards_screen import decide_rewards_screen, rewards_unclaimed

            if rewards_unclaimed(state):
                return decide_rewards_screen(state)
        return body
    if action == "play_card":
        if st in _COMBAT:
            try:
                from plugins.sts2.manual_mode import manual_mode_enabled
                from plugins.sts2.play_mode import agent_play_mode

                if agent_play_mode():
                    return _validate_play_card_agent(state, body)
                if manual_mode_enabled():
                    return _validate_play_card_manual(state, body)
            except Exception:
                pass
            from plugins.sts2.combat_survival_gate import forbid_non_survival_play

            gated = forbid_non_survival_play(state, body)
            if gated and gated.get("action") == "__pause__":
                return gated
            if gated:
                body = gated
            from plugins.sts2.combat_brain import (
                _card_is_block,
                block_play_is_urgent,
                incoming_attack_damage,
                prefer_block_play,
            )
            if block_play_is_urgent(state):
                forced = prefer_block_play(state)
                if forced:
                    return forced
            fixed = _fix_play_card(state, body)
            player = state.get("player") or {}
            hand = player.get("hand") or []
            try:
                idx = int(fixed.get("card_index", -1))
            except (TypeError, ValueError):
                idx = -1
            card = next((c for c in hand if c.get("index") == idx), None)
            inc = incoming_attack_damage(
                (state.get("battle") or {}).get("enemies") or []
            )
            blk = int(player.get("block", 0) or 0)
            if card and _card_is_block(card) and inc <= 0:
                from plugins.sts2.combat_brain import decide_combat
                return decide_combat(state, apply_lessons=True)
            if card and _card_is_block(card) and inc <= blk:
                from plugins.sts2.combat_brain import decide_combat
                return decide_combat(state, apply_lessons=True)
            return fixed
        return _fix_play_card(state, body)
    if action == "choose_map_node":
        return _fix_map_node(state, body)
    if action in ("claim_reward", "claim_treasure_relic"):
        return _fix_claim_reward(state, body)
    if action == "select_card_reward":
        return _fix_card_reward(state, body)
    if action == "select_card":
        return _fix_select_card(state, body)
    if action == "menu_select":
        return _fix_menu_select(state, body)
    if st == "event":
        return _fix_event(state, body)
    if action == "choose_event_option":
        return _fix_event(state, body)
    if action == "advance_dialogue":
        if st == "event":
            return body
        return _fallback(state)
    if st == "bundle_select":
        return _fix_bundle_select(state, body)
    if action == "use_potion":
        return _fix_potion(state, body)
    if action in ("choose_rest_option", "skip_rest_option", "skip_rest", "leave_rest"):
        return _fix_rest_site(state, body)
    if st == "rest_site" and action not in (
        "choose_rest_option",
        "proceed",
        "__wait__",
        "__pause__",
    ):
        return _fix_rest_site(state, body)
    if action == "__wait__" and st not in _COMBAT:
        fixed = _fallback(state)
        if fixed.get("action") not in ("__wait__", "__pause__"):
            return fixed
        return {"action": "proceed"}
    return body
def _fallback(state: dict) -> dict:
    from plugins.sts2.decision import _rule_action, _coerce_action, decide_combat
    st = str(state.get("state_type") or "")
    if st == "hand_select":
        from plugins.sts2.hand_select_brain import decide_hand_select
        return decide_hand_select(state)
    ruled = _rule_action(state)
    if ruled:
        return ruled
    if st in _COMBAT:
        return _coerce_action(state, decide_combat(state))
    if st == "game_over":
        from plugins.sts2.run_flow import next_menu_action
        return next_menu_action(state) or {
            "action": "menu_select",
            "option": "main_menu",
        }
    return {"action": "proceed"}
def _validate_play_card_agent(state: dict, body: dict) -> dict:
    """Agent-play: only legality (index/can_play/target) — never substitute or veto strategy."""
    hand = (state.get("player") or {}).get("hand") or []
    if not hand:
        return {"action": "__pause__"}
    try:
        idx = int(body.get("card_index", -1))
    except (TypeError, ValueError):
        return {"action": "__pause__"}
    card = next((c for c in hand if c.get("index") == idx), None)
    if card is None or not card.get("can_play", False):
        return {"action": "__pause__"}
    out = {"action": "play_card", "card_index": idx}
    tt = str(card.get("target_type") or "").lower()
    target = body.get("target")
    enemies = (state.get("battle") or {}).get("enemies") or []
    living = [e for e in enemies if int(e.get("hp", 0)) > 0]
    if tt in ("anyenemy", "enemy", "singleenemy") and living:
        if target and any(e.get("entity_id") == target for e in living):
            out["target"] = target
        else:
            out["target"] = min(
                living, key=lambda e: int(e.get("hp", 9999))
            ).get("entity_id")
    return out


def _validate_play_card_manual(state: dict, body: dict) -> dict:
    """Hand-play: reject illegal plays; never substitute another card_index."""
    from plugins.sts2.combat_survival_gate import play_card_would_lethal

    hand = (state.get("player") or {}).get("hand") or []
    if not hand:
        return {"action": "__pause__"}
    try:
        idx = int(body.get("card_index", -1))
    except (TypeError, ValueError):
        return {"action": "__pause__"}
    card = next((c for c in hand if c.get("index") == idx), None)
    if card is None or not card.get("can_play", False):
        return {"action": "__pause__"}
    probe = {"action": "play_card", "card_index": idx}
    if play_card_would_lethal(state, probe):
        return {"action": "__pause__"}
    out = dict(probe)
    tt = str(card.get("target_type") or "").lower()
    target = body.get("target")
    enemies = (state.get("battle") or {}).get("enemies") or []
    living = [e for e in enemies if int(e.get("hp", 0)) > 0]
    if tt in ("anyenemy", "enemy", "singleenemy") and living:
        if target and any(e.get("entity_id") == target for e in living):
            out["target"] = target
        else:
            out["target"] = min(
                living, key=lambda e: int(e.get("hp", 9999))
            ).get("entity_id")
    return out


def _fix_play_card(state: dict, body: dict) -> dict:
    from plugins.sts2.combat_survival_gate import must_survive_turn, pick_survival_card

    hand = (state.get("player") or {}).get("hand") or []
    if not hand:
        return _fallback(state)
    try:
        idx = int(body.get("card_index", -1))
    except (TypeError, ValueError):
        idx = -1
    card = next((c for c in hand if c.get("index") == idx), None)

    if must_survive_turn(state):
        surv = pick_survival_card(state, preferred_index=idx if card else None)
        if surv:
            return surv

    if card is None:
        playable = [c for c in hand if c.get("can_play")]
        if playable:
            from plugins.sts2.combat_brain import _card_is_block

            blocks = [c for c in playable if _card_is_block(c)]
            card = blocks[0] if blocks and must_survive_turn(state) else playable[0]
            idx = card.get("index", 0)
        else:
            return {"action": "end_turn"}
    if not card.get("can_play", False):
        playable = [c for c in hand if c.get("can_play")]
        if playable:
            from plugins.sts2.combat_brain import _card_is_block

            if must_survive_turn(state):
                blocks = [c for c in playable if _card_is_block(c)]
                card = blocks[0] if blocks else playable[0]
            else:
                card = playable[0]
            idx = card.get("index", 0)
        else:
            return {"action": "end_turn"}
    out = {"action": "play_card", "card_index": idx}
    tt = str(card.get("target_type") or "").lower()
    target = body.get("target")
    enemies = (state.get("battle") or {}).get("enemies") or []
    living = [e for e in enemies if int(e.get("hp", 0)) > 0]
    if tt in ("anyenemy", "enemy", "singleenemy") and living:
        if target and any(e.get("entity_id") == target for e in living):
            out["target"] = target
        else:
            out["target"] = min(living, key=lambda e: int(e.get("hp", 9999))).get("entity_id")
    return out
def _fix_map_node(state: dict, body: dict) -> dict:
    opts = (state.get("map") or {}).get("next_options") or state.get("next_options") or []
    if not opts:
        return {"action": "proceed"}
    try:
        ix = int(body.get("index", -1))
    except (TypeError, ValueError):
        ix = -1
    if any(o.get("index") == ix for o in opts):
        return {"action": "choose_map_node", "index": ix}
    from plugins.sts2.decision import _pick_map_node
    return _pick_map_node(opts, state)
def _fix_claim_reward(state: dict, body: dict) -> dict:
    from plugins.sts2.treasure_rewards import (
        decide_treasure_action,
        is_treasure_context,
        treasure_claim_body,
        treasure_claimables,
    )
    st = str(state.get("state_type") or "")
    if is_treasure_context(state):
        items = treasure_claimables(state)
        unclaimed = [it for it in items if not it.get("claimed") and not it.get("obtained")]
        if not unclaimed:
            return decide_treasure_action(state)
        try:
            ix = int(body.get("index", 0))
        except (TypeError, ValueError):
            ix = 0
        valid = {int(i.get("index", j)) for j, i in enumerate(unclaimed)}
        if ix not in valid and valid:
            ix = min(valid)
        return treasure_claim_body(state, ix)
    items = (state.get("rewards") or {}).get("items") or (state.get("rewards") or {}).get("options") or []
    if not items:
        return {"action": "proceed"}
    try:
        ix = int(body.get("index", 0))
    except (TypeError, ValueError):
        ix = 0
    valid = {int(i.get("index", j)) for j, i in enumerate(items) if isinstance(i, dict)}
    if ix not in valid and valid:
        ix = min(valid)
    return {"action": "claim_reward", "index": ix}
def _fix_card_reward(state: dict, body: dict) -> dict:
    from plugins.sts2.card_pick_brain import card_reward_can_skip
    from plugins.sts2.reward_cards import offer_reward_cards
    cards = offer_reward_cards(state)
    if not cards:
        from plugins.sts2.card_pick_brain import card_reward_should_skip
        if card_reward_can_skip(state) and card_reward_should_skip(state, []):
            return {"action": "proceed"}
        # Game often omits card list in JSON; index 0 still selects (see trajectories).
        return {"action": "select_card_reward", "card_index": 0}
    try:
        idx = int(body.get("card_index", body.get("index", 0)))
    except (TypeError, ValueError):
        idx = 0
    indices = {int(c.get("index", i)) for i, c in enumerate(cards)}
    if idx not in indices and indices:
        from plugins.sts2.decision import _pick_best_card
        picked = _pick_best_card(cards)
        idx = picked if picked is not None else min(indices)
    return {"action": "select_card_reward", "card_index": idx}
def _fix_select_card(state: dict, body: dict) -> dict:
    from plugins.sts2.card_pick_brain import card_select_should_confirm, rule_card_select_fallback
    from plugins.sts2.reward_cards import offer_reward_cards
    cs = state.get("card_select") or {}
    if card_select_should_confirm(state):
        return {"action": "confirm_selection"}
    cards = offer_reward_cards(state)
    if not cards:
        return {"action": "proceed"}
    try:
        idx = int(body.get("index", body.get("card_index", 0)))
    except (TypeError, ValueError):
        idx = 0
    indices = {int(c.get("index", i)) for i, c in enumerate(cards)}
    if idx not in indices and indices:
        _comm, fixed = rule_card_select_fallback(state)
        if isinstance(fixed, dict):
            return fixed
    return {"action": "select_card", "index": idx}
def _fix_event(state: dict, body: dict) -> dict:
    """Map menu_select/proceed/choose → legal event API actions."""
    from plugins.sts2.decision import _rule_action
    ev = state.get("event") or {}
    action = str(body.get("action") or "").strip()
    opts = [o for o in (ev.get("options") or []) if isinstance(o, dict)]
    pickable = [o for o in opts if not o.get("is_locked")]
    if action == "advance_dialogue":
        return body
    if action in ("menu_select", "proceed", "choose", "choose_option"):
        if ev.get("in_dialogue") and not pickable:
            return {"action": "advance_dialogue"}
        ruled = _rule_action(state)
        if ruled:
            return ruled
        if pickable:
            return {
                "action": "choose_event_option",
                "index": pickable[0].get("index", 0),
            }
        return {"action": "advance_dialogue"}
    if action == "choose_event_option":
        try:
            ix = int(body.get("index", body.get("option_index", -1)))
        except (TypeError, ValueError):
            ix = -1
        valid = {
            int(o.get("index", i))
            for i, o in enumerate(pickable)
            if not o.get("is_locked")
        }
        if ix in valid:
            return {"action": "choose_event_option", "index": ix}
        label = str(body.get("option") or body.get("title") or "").strip()
        if label:
            for o in pickable:
                if label in str(o.get("title") or ""):
                    return {
                        "action": "choose_event_option",
                        "index": o.get("index", 0),
                    }
        if pickable:
            return {
                "action": "choose_event_option",
                "index": pickable[0].get("index", 0),
            }
        return {"action": "advance_dialogue"}
    ruled = _rule_action(state)
    return ruled or body
def _fix_menu_select(state: dict, body: dict) -> dict:
    from plugins.sts2.safe_parse import normalize_options, option_enabled, option_label
    opt = str(body.get("option") or "").strip()
    opts = normalize_options(state.get("options") or [])
    names = []
    for o in opts:
        n = option_label(o)
        if n and option_enabled(o):
            names.append(n)
    if opt and opt in names:
        return {"action": "menu_select", "option": opt}
    for key in ("embark", "confirm", "continue", "singleplayer", "standard", "proceed"):
        if key in names:
            return {"action": "menu_select", "option": key}
    if names:
        return {"action": "menu_select", "option": names[0]}
    return _fallback(state)
def _fix_rest_site(state: dict, body: dict) -> dict:
    """Map hallucinated skip_rest_option → legal camp actions."""
    from plugins.sts2.safe_parse import normalize_options, option_enabled, option_label
    raw = (state.get("rest_site") or {}).get("options") or state.get("options") or []
    opts = normalize_options(raw)
    enabled = [o for o in opts if option_enabled(o)]
    if not enabled:
        return {"action": "proceed"}
    action = str(body.get("action") or "").strip()
    if action in ("skip_rest_option", "skip_rest", "leave_rest", "proceed"):
        from plugins.sts2.decision import _rule_action
        ruled = _rule_action(state)
        if ruled and ruled.get("action") == "choose_rest_option":
            return ruled
        return {"action": "choose_rest_option", "index": enabled[0].get("index", 0)}
    try:
        ix = int(body.get("index", body.get("option_index", -1)))
    except (TypeError, ValueError):
        ix = -1
    valid = {int(o.get("index", i)) for i, o in enumerate(enabled)}
    if ix in valid:
        return {"action": "choose_rest_option", "index": ix}
    label = str(body.get("option") or body.get("name") or "").strip().lower()
    if label:
        for o in enabled:
            oid = str(o.get("id", o.get("name", ""))).lower()
            olab = option_label(o).lower()
            if label in oid or label in olab or olab in label:
                return {"action": "choose_rest_option", "index": o.get("index", 0)}
    from plugins.sts2.decision import _rule_action
    ruled = _rule_action(state)
    if ruled:
        return ruled
    return {"action": "choose_rest_option", "index": enabled[0].get("index", 0)}
def _fix_bundle_select(state: dict, body: dict) -> dict:
    from plugins.sts2.bundle_select_brain import decide_bundle_select
    action = str(body.get("action") or "").strip()
    if action in ("proceed", "play_card", "end_turn", "menu_select", "select_card"):
        return decide_bundle_select(state)
    if action in ("confirm_selection", "cancel_selection"):
        bs = state.get("bundle_select") or {}
        if bs.get("preview_showing") or bs.get("can_confirm"):
            if action == "confirm_selection":
                return {"action": "confirm_bundle_selection"}
            if bs.get("can_cancel"):
                return {"action": "cancel_bundle_selection"}
    if action in ("select_bundle", "choose_bundle"):
        try:
            idx = int(body.get("index", body.get("bundle_index", 0)))
        except (TypeError, ValueError):
            idx = 0
        bs = state.get("bundle_select") or {}
        bundles = bs.get("bundles") or []
        if isinstance(bundles, list) and bundles:
            valid = {
                int(b.get("index", i))
                for i, b in enumerate(bundles)
                if isinstance(b, dict)
            }
            if valid and idx not in valid:
                idx = min(valid)
        return {"action": "select_bundle", "index": idx}
    if action not in (
        "confirm_bundle_selection",
        "cancel_bundle_selection",
        "__wait__",
        "__pause__",
    ):
        return decide_bundle_select(state)
    return body
def _fix_potion(state: dict, body: dict) -> dict:
    from plugins.sts2.combat_brain import combat_should_wait
    if combat_should_wait(state):
        return {"action": "__wait__"}
    try:
        slot = int(body.get("slot", 0))
    except (TypeError, ValueError):
        slot = 0
    pots = (state.get("player") or {}).get("potions") or []
    if not any(pots):
        return _fallback(state)
    def _usable(pot: Any) -> bool:
        if not pot or not isinstance(pot, dict):
            return False
        if pot.get("can_use_in_combat") is False:
            return False
        return True
    if 0 <= slot < len(pots) and _usable(pots[slot]):
        out = {"action": "use_potion", "slot": slot}
        if body.get("target"):
            out["target"] = body["target"]
        return out
    for i, p in enumerate(pots):
        if _usable(p):
            out = {"action": "use_potion", "slot": i}
            if body.get("target"):
                out["target"] = body["target"]
            return out
    return _fallback(state)