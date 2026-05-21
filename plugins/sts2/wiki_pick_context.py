"""Wiki-first context for card pick / smith upgrade (构筑 + 局势 + 经验)."""

from __future__ import annotations

import logging
from typing import Any

from plugins.sts2.reward_cards import offer_reward_cards

logger = logging.getLogger(__name__)


def situation_context(state: dict) -> str:
    """Current run situation — not just deck list."""
    run = state.get("run") or {}
    player = state.get("player") or {}
    try:
        hp = int(player.get("hp", player.get("current_hp", 0)))
        mx = int(player.get("max_hp", hp) or hp or 1)
    except (TypeError, ValueError):
        hp, mx = 0, 1
    ratio = hp / mx if mx > 0 else 0.0
    try:
        floor = int(run.get("floor") or 0)
    except (TypeError, ValueError):
        floor = 0
    act = run.get("act", "?")
    gold = run.get("gold", "?")
    asc = run.get("ascension", "")

    relics = player.get("relics") or []
    relic_names = []
    for r in relics[:8]:
        if isinstance(r, dict):
            relic_names.append(str(r.get("name") or r.get("id") or "?"))
        else:
            relic_names.append(str(r))

    st = str(state.get("state_type") or "")
    pressure = "血线危险，优先生存/格挡。" if ratio < 0.45 else ""
    if ratio > 0.75 and floor >= 8:
        pressure = (pressure + " 血线健康，可贪成长/伤害。").strip()

    return (
        f"局势: Act{act} 第{floor}层 HP {hp}/{mx} ({ratio:.0%}) 金{gold} "
        f"进阶{asc} 界面={st}"
        + (f" 遗物: {', '.join(relic_names)}" if relic_names else "")
        + (f" | {pressure}" if pressure else "")
    )


def _card_ids(cards: list[dict]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for c in cards:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "").strip().upper()
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def prefetch_wiki_for_pick(
    state: dict,
    *,
    offers: list[dict] | None = None,
    extra_deck_ids: int = 3,
    max_fetches: int | None = None,
) -> dict[str, Any]:
    """
    Pull wiki into local knowledge/ before LLM pick.
    Returns stats {fetched, cached, ids}.
    """
    from plugins.sts2.config import load_sts2_config
    from plugins.sts2.knowledge import fetch_and_store, has_entry

    cfg = load_sts2_config()
    if not cfg.get("study_card_pick_wiki_first", True):
        return {"skipped": True}

    limit = max_fetches
    if limit is None:
        try:
            limit = int(cfg.get("study_card_pick_wiki_max_fetches", 6))
        except (TypeError, ValueError):
            limit = 6

    use_llm = bool(cfg.get("knowledge_use_llm", True))
    offers = offers if offers is not None else offer_reward_cards(state)

    ids_ordered: list[str] = _card_ids(offers)

    # Also wiki top deck staples (for 构筑连贯)
    from plugins.sts2.card_pick_brain import _collect_deck_cards

    deck = _collect_deck_cards(state)
    deck_ids = _card_ids(deck)
    for cid in deck_ids:
        if cid not in ids_ordered:
            ids_ordered.append(cid)

    fetched: list[str] = []
    cached: list[str] = []
    budget = max(0, limit)

    for cid in ids_ordered:
        if has_entry("cards", cid):
            cached.append(cid)
            continue
        if budget <= 0:
            break
        name = cid
        for c in offers + deck:
            if isinstance(c, dict) and str(c.get("id", "")).upper() == cid:
                name = str(c.get("name") or cid)
                break
        ent, _rule = fetch_and_store("cards", cid, query=name, use_llm=use_llm)
        if ent:
            fetched.append(cid)
            budget -= 1

    return {
        "fetched": fetched,
        "cached": cached,
        "examined": len(ids_ordered),
        "offer_ids": _card_ids(offers),
    }


def wiki_dossier_for_cards(card_ids: list[str], *, max_entries: int = 12) -> str:
    """Formatted wiki + distilled rules for prompt injection."""
    from plugins.sts2.knowledge import get_entry

    lines: list[str] = []
    for cid in card_ids[:max_entries]:
        ent = get_entry("cards", cid)
        if not ent:
            lines.append(f"- {cid}: （本地无 Wiki，决策前应先查 wiki 或保守跳过）")
            continue
        name = ent.get("name") or cid
        tags = ", ".join(ent.get("tags") or []) or "?"
        rule = str(ent.get("rule") or "").strip()
        snippet = str(ent.get("wiki_snippet") or ent.get("description") or "")[:280]
        lines.append(
            f"- {name} [{cid}] 标签:{tags}\n"
            f"  经验规则: {rule or '（无）'}\n"
            f"  Wiki: {snippet or '（无摘要）'}"
        )
    if not lines:
        return "Wiki: （无卡牌条目）"
    return "Wiki / 理解（先读再选，勿臆测）:\n" + "\n".join(lines)


def build_pick_context(
    state: dict,
    *,
    offers: list[dict] | None = None,
) -> str:
    """Full block: 局势 + wiki prefetch + dossier + strategy knowledge rules."""
    from plugins.sts2.knowledge import list_rules_from_knowledge
    from plugins.sts2.notes import recall_block

    offers = offers if offers is not None else offer_reward_cards(state)
    stats = prefetch_wiki_for_pick(state, offers=offers)
    offer_ids = stats.get("offer_ids") or _card_ids(offers)

    # Deck-relevant ids for context (offers first)
    from plugins.sts2.card_pick_brain import _collect_deck_cards

    dossier_ids = list(offer_ids)
    for cid in _card_ids(_collect_deck_cards(state)):
        if cid not in dossier_ids and len(dossier_ids) < 14:
            dossier_ids.append(cid)

    parts = [
        situation_context(state),
        wiki_dossier_for_cards(dossier_ids),
    ]
    if stats.get("fetched"):
        parts.append(f"（本步新拉 Wiki: {', '.join(stats['fetched'][:8])}）")

    krules = list_rules_from_knowledge(limit=8)
    if krules:
        parts.append("构筑经验摘录:\n" + "\n".join(f"- {r}" for r in krules))

    recall = recall_block()
    if recall:
        parts.append(recall[:2500])

    return "\n\n".join(parts)
