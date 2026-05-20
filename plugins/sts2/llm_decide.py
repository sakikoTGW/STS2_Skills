"""Study-mode LLM decisions — model thinks, rules validate."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from plugins.sts2.visibility import describe_action, describe_situation

logger = logging.getLogger(__name__)

_COMBAT = frozenset({"monster", "elite", "boss", "hand_select"})


def _parse_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
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


def _allowed_actions_hint(state: dict) -> str:
    st = str(state.get("state_type") or "")
    if st in _COMBAT:
        return (
            "Allowed: play_card (card_index, optional target), end_turn ONLY on player turn "
            "with no better plays, use_potion (slot), __wait__ on enemy turn. "
            "FORBIDDEN: proceed, menu_select, choose_map_node."
        )
    if st == "map":
        opts = (state.get("map") or {}).get("next_options") or state.get("next_options") or []
        bits = []
        for o in opts[:8]:
            if isinstance(o, dict):
                bits.append(f"#{o.get('index')} {o.get('type', o.get('label', '?'))}")
        extra = (
            " Plan full-act route from play_brief 【路线规划】stats + adopted rules; "
            "elite greed only when data supports (Ironclad Act1 may be strong but not always)."
        )
        return (
            "Allowed: choose_map_node with index from: "
            + (", ".join(bits) or "see state")
            + extra
        )
    if st == "card_reward":
        return "Allowed: select_card_reward (card_index), proceed/skip if skip offered."
    if st == "rewards":
        return (
            "Allowed: claim_reward (index) for EACH unclaimed item (gold before card). "
            "FORBIDDEN: proceed while any reward item is unclaimed."
        )
    if st == "event":
        return "Allowed: choose_event_option (index), advance_dialogue, proceed."
    if st in ("treasure", "fake_merchant"):
        return (
            "Allowed: claim_treasure_relic (index) for each relic — NOT claim_reward. "
            "Then proceed when can_proceed."
        )
    if st in ("relic_select", "relic_select_boss"):
        if state.get("treasure"):
            return "Treasure chest: claim_treasure_relic (index), then proceed."
        return "Allowed: select_relic (index)."
    if st == "rest_site":
        return (
            "Allowed: choose_rest_option (index from rest_site.options). "
            "Heal when HP low, else smith/upgrade. "
            "If options is [] and can_proceed use proceed (do not choose_rest_option). "
            "FORBIDDEN: skip_rest_option (not a real API action)."
        )
    if st == "menu":
        return "Allowed: menu_select (option exact string), proceed."
    if st == "bundle_select":
        return (
            "FORBIDDEN: proceed unless state.bundle_select.can_proceed is true. "
            "Use select_bundle(index) then confirm_bundle_selection when preview_showing; "
            "never menu_select/proceed unless bundle_select.can_proceed is true."
        )
    if st == "crystal_sphere":
        from plugins.sts2.crystal_sphere import crystal_sphere_stale_map, crystal_sphere_stuck

        extra = ""
        if crystal_sphere_stale_map(state):
            extra = (
                " STALE: map next_options exist — if user says already on map, "
                "use choose_map_node(index); do NOT click more cells."
            )
        if crystal_sphere_stuck(state):
            extra += (
                " STUCK: charges=0, can_proceed=false — use crystal_sphere_proceed "
                "or choose_map_node; NEVER click_cell."
            )
        return (
            "Allowed: crystal_sphere_set_tool(tool=big|small), "
            "crystal_sphere_click_cell(x,y) only while divinations_remaining>0, "
            "crystal_sphere_proceed when can_proceed, choose_map_node if map data present. "
            "FORBIDDEN: proceed, divine, big, small as action names; play_card; menu_select."
            + extra
        )
    return "Allowed: proceed, or action matching state_type in API docs."


def _compact_state(state: dict) -> str:
    """Situation text + small JSON slice for indices only."""
    base = describe_situation(state)
    st = str(state.get("state_type") or "")
    extra: Dict[str, Any] = {"state_type": st}
    if st == "map":
        opts = (state.get("map") or {}).get("next_options") or state.get("next_options")
        extra["next_options"] = opts
    elif st in ("card_reward", "card_select"):
        from plugins.sts2.reward_cards import offer_reward_cards

        extra["cards"] = offer_reward_cards(state)
    elif st in ("relic_select", "relic_select_boss"):
        extra["relics"] = (state.get("relic_select") or {}).get("relics")
    elif st == "rest_site":
        extra["rest_site"] = (state.get("rest_site") or {}).get("options") or state.get(
            "options"
        )
    elif st in _COMBAT:
        extra["battle"] = {
            "turn": (state.get("battle") or {}).get("turn"),
            "is_play_phase": (state.get("battle") or {}).get("is_play_phase"),
        }
        extra["hand"] = (state.get("player") or {}).get("hand")
        extra["enemies"] = [
            {
                "entity_id": e.get("entity_id"),
                "name": e.get("name"),
                "hp": e.get("hp"),
                "intents": e.get("intents"),
            }
            for e in ((state.get("battle") or {}).get("enemies") or [])[:6]
            if isinstance(e, dict)
        ]
    slice_json = json.dumps(extra, ensure_ascii=False)[:6000]
    return f"{base}\n\nAPI slice:\n{slice_json}"


def llm_decide_step(
    state: dict,
    *,
    user_hint: str = "",
    memory: str = "",
) -> Tuple[str, dict, bool]:
    """
    Ask auxiliary LLM for one action. Returns (commentary, body, success).
  On failure body is {} and success False.
    """
    from plugins.sts2.config import load_sts2_config

    cfg = load_sts2_config()
    if not cfg.get("study_use_llm", True):
        return "", {}, False

    st = str(state.get("state_type") or "")
    situation = _compact_state(state)
    recall = memory[:3500] if memory else ""
    try:
        from plugins.sts2.notes import recall_block

        if not recall:
            recall = recall_block()[:3500]
    except Exception:
        pass

    from plugins.sts2.thinking_policy import map_system_append

    system = (
        "You are an expert Slay the Spire 2 player controlling via HTTP API. "
        "Goal: clear Act1, Act2, Act3 in one run. "
        "Respond with ONLY one JSON object, no markdown:\n"
        '{"commentary":"detailed Chinese reasoning",'
        '"action":"...", ...params}\n'
        "Use ONLY legal actions for this screen. Indices must come from the state."
        + map_system_append()
    )
    from plugins.sts2.knowledge_pack import assemble_decide_pack

    knowledge = ""
    try:
        from plugins.sts2.reward_cards import offer_reward_cards

        offers = offer_reward_cards(state) if st in ("card_reward", "card_select") else None
        knowledge = assemble_decide_pack(state, offers=offers)
    except Exception:
        knowledge = ""
    user = (
        f"Screen: {st}\n{_allowed_actions_hint(state)}\n\n"
        f"{situation}\n\n"
    )
    if knowledge:
        user += f"{knowledge}\n\n"
    brief = str(state.get("_decision_brief") or "").strip()
    if brief:
        user += f"【统一决策上下文】\n{brief[:4000]}\n\n"
    if recall:
        user += f"Memory / lessons:\n{recall}\n\n"
    if user_hint:
        user += f"Hint: {user_hint}\n\n"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        from plugins.sts2.llm_util import sts2_call_llm
        from plugins.sts2.thinking_policy import commentary_substantive, llm_retry_user

        raw = sts2_call_llm(
            messages,
            max_tokens=int(cfg.get("study_llm_max_tokens", 720)),
            temperature=float(cfg.get("study_llm_temperature", 0.3)),
        )
        parsed_probe = _parse_json(raw)
        comm_probe = str((parsed_probe or {}).get("commentary") or "")
        if parsed_probe and not commentary_substantive(comm_probe, combat=st in _COMBAT):
            raw2 = sts2_call_llm(
                messages
                + [
                    {"role": "assistant", "content": (raw or "")[:800]},
                    {
                        "role": "user",
                        "content": llm_retry_user("思考过短，请写清路线/意图/算数/取舍"),
                    },
                ],
                max_tokens=int(cfg.get("study_llm_max_tokens", 720)),
                temperature=float(cfg.get("study_llm_temperature", 0.3)),
            )
            if raw2:
                raw = raw2
    except Exception as exc:
        logger.warning("study LLM call failed: %s", exc)
        return "", {}, False

    parsed = _parse_json(raw)
    if not parsed:
        logger.debug("study LLM unparseable: %s", raw[:200])
        return "", {}, False

    commentary = str(parsed.pop("commentary", "") or "模型决策。").strip()
    action = str(parsed.get("action") or "").strip()
    if not action:
        return commentary, {}, False

    body = dict(parsed)
    body["action"] = action

    from plugins.sts2.action_validate import validate_action
    from plugins.sts2.decision import _coerce_action

    body = validate_action(state, body)
    body = _coerce_action(state, body)

    if body.get("action") in ("__pause__",):
        return commentary, {}, False

    plan = describe_action(state, body)
    full_comm = f"{commentary}\n▶ {plan}"
    return full_comm, body, True
