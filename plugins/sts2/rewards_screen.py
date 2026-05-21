"""Post-combat rewards screen — claim every item before proceed."""

from __future__ import annotations

from typing import Any

# Gold first (instant), then card/relic/potion (may open sub-screens).
_CLAIM_PREF = ("gold", "card", "relic", "potion")


def rewards_items(state: dict) -> list[dict]:
    rw = state.get("rewards") or {}
    raw = rw.get("items") or rw.get("options") or []
    return [i for i in raw if isinstance(i, dict)]


def rewards_unclaimed(state: dict) -> list[dict]:
    return [
        i
        for i in rewards_items(state)
        if not i.get("claimed") and not i.get("obtained") and not i.get("picked")
    ]


def _matches_pref(item: dict, pref: str) -> bool:
    itype = str(item.get("type", "")).lower()
    if itype == pref:
        return True
    return pref in itype


def decide_rewards_screen(state: dict) -> dict[str, Any]:
    """Next legal action on the rewards screen."""
    unclaimed = rewards_unclaimed(state)
    if not unclaimed:
        return {"action": "proceed"}
    for pref in _CLAIM_PREF:
        for item in unclaimed:
            if _matches_pref(item, pref):
                return {"action": "claim_reward", "index": int(item.get("index", 0))}
    return {"action": "claim_reward", "index": int(unclaimed[0].get("index", 0))}


def format_rewards_brief(state: dict) -> str:
    """play_brief block for rewards / card_reward discipline."""
    rw = state.get("rewards") or {}
    unclaimed = rewards_unclaimed(state)
    lines = ["【战后奖励屏】"]
    if not unclaimed:
        lines.append("已全部领取 → 才可 proceed。")
        if rw.get("can_proceed") is False:
            lines.append("can_proceed=false：先 claim_reward 再试。")
        return "\n".join(lines)
    lines.append("禁止 proceed：还有未领奖励。顺序建议：金币 → 卡牌 → 遗物 → 药水。")
    for it in unclaimed[:8]:
        ix = it.get("index", "?")
        typ = it.get("type", "?")
        name = it.get("name") or it.get("label") or ""
        extra = f" ({name})" if name else ""
        lines.append(f"  [{ix}] {typ}{extra} → claim_reward(index={ix})")
    lines.append("领完最后一项后再 proceed（卡牌会进 select_card_reward 子屏）。")
    return "\n".join(lines)


def format_rewards_commentary(state: dict, body: dict) -> str:
    from plugins.sts2.visibility import describe_action

    brief = format_rewards_brief(state)
    return f"{brief}\n▶ {describe_action(state, body)}"
