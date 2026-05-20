"""Extract combat runtime counters from MCP / gateway state."""

from __future__ import annotations

from typing import Any, Dict


def combat_runtime(state: dict | None) -> Dict[str, Any]:
    if not state:
        return {}
    battle = state.get("battle") or {}
    player = state.get("player") or {}
    combat = state.get("combat") or {}

    def _int(*keys: str) -> int:
        for src in (battle, player, combat, state):
            if not isinstance(src, dict):
                continue
            for k in keys:
                if src.get(k) is not None:
                    try:
                        return int(src[k])
                    except (TypeError, ValueError):
                        pass
        return 0

    return {
        "cards_played_this_turn": _int(
            "cards_played_this_turn", "cardsPlayedThisTurn", "cards_played"
        ),
        "attacks_played_this_turn": _int(
            "attacks_played_this_turn", "attacksPlayedThisTurn", "attacks_played"
        ),
        "hit_from_behind": bool(
            battle.get("hit_from_behind")
            or battle.get("surrounded_backstab")
            or player.get("hit_from_behind")
        ),
    }


def merge_context_into_damage_ctx(ctx: Any, state: dict | None) -> None:
    if state is None:
        return
    rt = combat_runtime(state)
    if not ctx.cards_played_this_turn:
        ctx.cards_played_this_turn = int(rt.get("cards_played_this_turn") or 0)
    if not ctx.attacks_played_this_turn:
        ctx.attacks_played_this_turn = int(rt.get("attacks_played_this_turn") or 0)
    if not ctx.hit_from_behind:
        ctx.hit_from_behind = bool(rt.get("hit_from_behind"))
