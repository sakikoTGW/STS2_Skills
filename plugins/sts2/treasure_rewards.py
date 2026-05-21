"""Parse treasure / chest screens — API action is claim_treasure_relic (not claim_reward)."""

from __future__ import annotations

from typing import Any

TREASURE_CLAIM_ACTION = "claim_treasure_relic"


def is_treasure_context(state: dict) -> bool:
    if not state:
        return False
    st = str(state.get("state_type") or "")
    if st in ("treasure", "fake_merchant"):
        return True
    if st == "relic_select" and (state.get("treasure") or state.get("treasure_room")):
        return True
    screen = state.get("screen")
    if isinstance(screen, dict) and "treasure" in str(screen.get("type") or "").lower():
        return True
    return False


def treasure_claim_action(state: dict) -> str:
    """POST action name for taking chest / treasure relic."""
    if str(state.get("state_type") or "") == "relic_select" and not state.get("treasure"):
        return "select_relic"
    return TREASURE_CLAIM_ACTION


def treasure_claim_body(state: dict, index: int) -> dict:
    return {"action": treasure_claim_action(state), "index": int(index)}


def _extend_items(raw: Any, out: list[dict]) -> None:
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                out.append(item)
    elif isinstance(raw, dict) and (raw.get("id") or raw.get("name") or raw.get("type")):
        out.append(raw)


def treasure_claimables(state: dict) -> list[dict]:
    """Relics/cards/gold offered in a treasure room (many API shapes)."""
    if not state:
        return []
    out: list[dict] = []
    tr = state.get("treasure") or {}
    for key in (
        "relics",
        "cards",
        "items",
        "choices",
        "rewards",
        "relic",
        "gold",
        "potion",
        "potions",
        "displayed_relics",
        "displayed_cards",
    ):
        _extend_items(tr.get(key), out)
    for key in ("relics", "items", "choices"):
        _extend_items(state.get(key), out)
    rs = state.get("relic_select") or {}
    if isinstance(rs, dict):
        _extend_items(rs.get("relics"), out)
    rw = state.get("rewards") or {}
    for item in rw.get("items") or []:
        if not isinstance(item, dict):
            continue
        itype = str(item.get("type", "")).lower()
        if itype in ("relic", "card", "gold", "potion", "treasure"):
            _extend_items(item.get("relics") or item.get("items") or [item], out)
        elif item.get("id") or item.get("name"):
            out.append(item)
    screen = state.get("screen")
    if isinstance(screen, dict):
        for key in ("relics", "cards", "items", "choices"):
            _extend_items(screen.get(key), out)
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for i, item in enumerate(out):
        key = (item.get("index", i), str(item.get("id") or ""), str(item.get("name") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _item_unclaimed(item: dict) -> bool:
    if item.get("claimed") or item.get("obtained") or item.get("picked"):
        return False
    if item.get("taken") is True:
        return False
    return True


def format_treasure_offers(state: dict) -> str:
    items = treasure_claimables(state)
    if not items:
        tr = state.get("treasure") or {}
        if tr.get("can_proceed") is False:
            return (
                "宝箱: (未解析到物品) — 尝试 claim_treasure_relic index=0 "
                "或 menu_select 打开"
            )
        return "宝箱: (未解析到物品)"
    parts = []
    for i, it in enumerate(items[:8]):
        idx = it.get("index", i)
        name = str(it.get("name") or it.get("id") or "?")
        itype = str(it.get("type") or "")
        parts.append(f"#{idx} {name}" + (f" ({itype})" if itype else ""))
    return "宝箱: " + " | ".join(parts)


def decide_treasure_action(state: dict) -> dict:
    """Always take chest loot before proceed."""
    from plugins.sts2.safe_parse import normalize_options, option_enabled, option_label

    items = treasure_claimables(state)
    unclaimed = [it for it in items if _item_unclaimed(it)]
    if unclaimed:
        ix = int(unclaimed[0].get("index", 0))
        return treasure_claim_body(state, ix)

    tr = state.get("treasure") or {}
    if tr.get("can_proceed") is False or items:
        return treasure_claim_body(state, 0)

    opts = normalize_options(state.get("options") or tr.get("options") or [])
    for prefer in ("open", "take", "claim", "confirm", "continue", "proceed"):
        for o in opts:
            if option_enabled(o) and option_label(o).lower() == prefer:
                lab = option_label(o)
                if prefer in ("open", "take", "claim", "confirm"):
                    return {"action": "menu_select", "option": lab}
                return {"action": "menu_select", "option": lab}
    if opts and option_enabled(opts[0]):
        return {"action": "menu_select", "option": option_label(opts[0])}
    if tr.get("can_proceed", True) and not items:
        return {"action": "proceed"}
    return treasure_claim_body(state, 0)
