"""Parse card-offer screens (card_reward / card_select) from API state."""

from __future__ import annotations

from typing import Any


def offer_reward_cards(state: dict) -> list[dict]:
    """Cards offered on card_reward or card_select screens."""
    if not state:
        return []
    st = str(state.get("state_type") or "").lower()
    raw: list[Any] = []

    def _extend(candidates: Any) -> None:
        if isinstance(candidates, list):
            raw.extend(c for c in candidates if isinstance(c, dict))
        elif isinstance(candidates, dict) and candidates.get("id"):
            raw.append(candidates)

    if st == "card_reward" or state.get("card_reward"):
        block = state.get("card_reward") or {}
        for key in (
            "cards",
            "choices",
            "options",
            "offers",
            "reward_cards",
            "card_choices",
            "displayed_cards",
            "draft_options",
        ):
            _extend(block.get(key))
        _extend(state.get("cards"))
        _extend(state.get("choices"))
        screen = state.get("screen")
        if isinstance(screen, dict):
            for key in ("cards", "choices", "options"):
                _extend(screen.get(key))
        rw = state.get("rewards") or {}
        for item in rw.get("items") or []:
            if not isinstance(item, dict):
                continue
            itype = str(item.get("type", "")).lower()
            if itype in ("card", "card_reward", "add_card"):
                _extend(item.get("cards") or item.get("choices"))
                if item.get("id"):
                    _extend([item])

    if st == "card_select" or state.get("card_select"):
        block = state.get("card_select") or {}
        for key in ("cards", "choices", "options"):
            _extend(block.get(key))

    # De-dupe by index/id
    seen: set[tuple] = set()
    out: list[dict] = []
    for c in raw:
        key = (c.get("index"), str(c.get("id") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def format_card_offers(cards: list[dict]) -> str:
    if not cards:
        return "选卡: (API 未返回卡牌列表)"
    parts = []
    for c in cards:
        idx = c.get("index", "?")
        name = str(c.get("name") or c.get("id") or "?")
        rid = str(c.get("id") or "")
        rare = str(c.get("rarity") or "")
        tail = f" [{rid}]" if rid and rid not in name else ""
        parts.append(f"#{idx} {name}{tail}" + (f" ({rare})" if rare else ""))
    return "选卡: " + " | ".join(parts)
