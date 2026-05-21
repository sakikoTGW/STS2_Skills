"""Merchant pricing + card removal cost."""

from __future__ import annotations

from typing import Any

from plugins.sts2.game_flow_kb.ascension import _ascension_level
from plugins.sts2.game_flow_kb.store import merchant_data
from plugins.sts2.mechanics_kb.power_parse import relic_active


def _removal_times(state: dict) -> int:
    run = state.get("run") or {}
    shop = state.get("shop") or {}
    for key in (
        "merchant_remove_count",
        "card_remove_count",
        "removals_purchased",
        "remove_purchases",
    ):
        if run.get(key) is not None:
            try:
                return max(0, int(run[key]))
            except (TypeError, ValueError):
                pass
        if shop.get(key) is not None:
            try:
                return max(0, int(shop[key]))
            except (TypeError, ValueError):
                pass
    return 0


def card_removal_cost(state: dict) -> dict[str, Any]:
    """Next card removal gold cost (wiki + ascension 6)."""
    m = merchant_data()
    cr = m.get("card_removal") or {}
    lvl = _ascension_level(state)
    times = _removal_times(state)
    if lvl >= 6:
        base = int(cr.get("ascension_6_base_cost") or 100)
        inc = int(cr.get("ascension_6_increment") or 50)
    else:
        base = int(cr.get("base_cost") or 75)
        inc = int(cr.get("increment_per_purchase") or 25)
    raw = base + inc * times

    player = state.get("player") or {}
    mult = 1.0
    notes: list[str] = []
    for ent in m.get("relic_interactions") or []:
        rid = ent.get("id")
        if not rid or not relic_active(player, str(rid)):
            continue
        if ent.get("effect") == "all_prices_multiplier":
            mult *= float(ent.get("value") or 1.0)
            notes.append(f"{rid}×{ent.get('value')}")
    if relic_active(player, "MEMBERSHIP_CARD") and relic_active(player, "THE_COURIER"):
        mult = 0.4
        notes.append("会员+送货员=40%标价")

    final = max(0, int(raw * mult))
    return {
        "raw_cost": raw,
        "final_cost": final,
        "times_already_bought": times,
        "ascension_6": lvl >= 6,
        "price_multiplier": mult,
        "notes": notes,
        "once_per_shop": bool(cr.get("once_per_shop")),
    }


def format_merchant_brief(state: dict) -> str:
    m = merchant_data()
    if not m:
        return ""
    lines = ["【商人·wiki 知识库】"]
    prices = m.get("prices") or {}
    lines.append(
        "  牌价: 普"
        f"{prices.get('card_common', '?')}"
        f" / 罕{prices.get('card_uncommon', '?')}"
        f" / 稀{prices.get('card_rare', '?')} 金"
    )
    lines.append(
        "  遗物: 店"
        f"{prices.get('relic_shop', '?')}"
        f" 普{prices.get('relic_common', '?')}"
        f" 罕{prices.get('relic_uncommon', '?')}"
    )
    rc = card_removal_cost(state)
    lines.append(
        f"  删牌: 下次≈{rc['final_cost']}金"
        f" (已删{rc['times_already_bought']}次"
        + (", A6通胀" if rc.get("ascension_6") else "")
        + ")"
    )
    if rc.get("notes"):
        lines.append("  遗物折价: " + ", ".join(rc["notes"]))
    for hint in (m.get("agent_hints") or [])[:3]:
        lines.append(f"  · {hint}")
    shop = state.get("shop") or {}
    gold = (state.get("run") or {}).get("gold")
    if gold is not None:
        lines.append(f"  当前金币: {gold}")
    cards = shop.get("cards") or []
    relics = shop.get("relics") or []
    if cards or relics:
        lines.append(f"  货架: {len(cards)}牌 {len(relics)}遗物")
    return "\n".join(lines)
