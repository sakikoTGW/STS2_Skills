"""Combat hand_select: Armaments upgrade, Survivor discard, etc."""

from __future__ import annotations

from plugins.sts2.decision import _CARD_PRIORITY, _knowledge_reward_adjustment


def _upgrade_score(card: dict, state: dict | None = None) -> float:
    if state:
        try:
            from plugins.sts2.upgrade_advisor import score_upgrade

            return score_upgrade(card, state)
        except Exception:
            pass
    rid = str(card.get("id", "")).upper()
    name = str(card.get("name", ""))
    score = float(_CARD_PRIORITY.get(rid, 15))
    score += float(_knowledge_reward_adjustment(rid))
    if card.get("is_upgraded"):
        score -= 500
    if "痛击" in name or rid == "BASH":
        score += 40
    if "防御" in name or "DEFEND" in rid:
        score += 5
    if "打击" in name or "STRIKE" in rid:
        score -= 2
    return score


def _discard_score(card: dict) -> float:
    """Lower = discard first."""
    return _upgrade_score(card)


def decide_hand_select(state: dict) -> dict:
    hs = state.get("hand_select") or {}
    if hs.get("can_confirm", False):
        return {"action": "combat_confirm_selection"}

    cards: list[dict] = [c for c in (hs.get("cards") or []) if isinstance(c, dict)]
    if not cards:
        return {"action": "combat_confirm_selection"}

    mode = str(hs.get("mode", "")).lower()
    prompt = str(hs.get("prompt", ""))
    is_upgrade = mode == "upgrade_select" or "升级" in prompt

    if is_upgrade:
        pick = max(
            cards,
            key=lambda c: (_upgrade_score(c, state), -int(c.get("index", 0))),
        )
    else:
        pick = min(cards, key=lambda c: (_discard_score(c), int(c.get("index", 0))))

    return {"action": "combat_select_card", "card_index": int(pick.get("index", 0))}


def hand_select_commentary(state: dict, body: dict) -> str:
    hs = state.get("hand_select") or {}
    mode = str(hs.get("mode", ""))
    prompt = str(hs.get("prompt", ""))[:80]
    act = body.get("action", "?")
    if act == "combat_confirm_selection":
        return f"【武装/选牌】确认选择（{prompt or mode}）"
    idx = body.get("card_index", "?")
    cards = hs.get("cards") or []
    name = next(
        (c.get("name") for c in cards if c.get("index") == idx),
        "?",
    )
    verb = "升级" if "upgrade" in mode or "升级" in prompt else "选中"
    return f"【武装/选牌】{verb} [{idx}]{name}（{prompt or mode}）"
