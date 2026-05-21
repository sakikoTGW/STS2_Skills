"""Auto-curate wiki knowledge from live game state (study / marathon)."""

from __future__ import annotations

import logging
from typing import Any

from plugins.sts2.config import load_sts2_config
from plugins.sts2.knowledge import fetch_and_store, has_entry
from plugins.sts2.notes import merge_strategy_rules

logger = logging.getLogger(__name__)

_CardRef = tuple[str, str, str]  # kind, id, display name


def _card_ref(card: dict) -> _CardRef | None:
    if not isinstance(card, dict):
        return None
    cid = str(card.get("id") or "").strip()
    if not cid:
        return None
    name = str(card.get("name") or cid)
    return ("cards", cid.upper(), name)


def _relic_ref(relic: dict) -> _CardRef | None:
    if not isinstance(relic, dict):
        return None
    rid = str(relic.get("id") or relic.get("relic_id") or "").strip()
    if not rid:
        return None
    name = str(relic.get("name") or rid)
    return ("relics", rid.upper(), name)


def collect_unknown_items(state: dict) -> list[_CardRef]:
    """Items in current state not yet in local knowledge/."""
    seen: set[tuple[str, str]] = set()
    out: list[_CardRef] = []

    def add(ref: _CardRef | None) -> None:
        if not ref:
            return
        kind, cid, _name = ref
        key = (kind, cid)
        if key in seen or has_entry(kind, cid):
            return
        seen.add(key)
        out.append(ref)

    player = state.get("player") or {}
    for card in player.get("hand") or []:
        add(_card_ref(card))
    for card in player.get("draw_pile") or []:
        add(_card_ref(card))
    for card in player.get("discard_pile") or []:
        add(_card_ref(card))

    cr = state.get("card_reward") or {}
    for card in cr.get("cards") or []:
        add(_card_ref(card))

    cs = state.get("card_select") or {}
    for card in cs.get("cards") or cs.get("choices") or []:
        add(_card_ref(card))

    rewards = state.get("rewards") or {}
    for item in rewards.get("items") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).lower() == "relic":
            add(_relic_ref(item))
        elif str(item.get("type", "")).lower() == "card":
            add(_card_ref(item))

    for relic in player.get("relics") or []:
        add(_relic_ref(relic if isinstance(relic, dict) else {"id": relic}))

    shop = state.get("shop") or {}
    for card in shop.get("cards") or []:
        add(_card_ref(card))
    for relic in shop.get("relics") or []:
        add(_relic_ref(relic))

    return out


def curate_from_state(
    state: dict,
    *,
    use_llm: bool | None = None,
    max_items: int | None = None,
    merge_rules: bool = True,
) -> dict[str, Any]:
    """Fetch wiki for unseen cards/relics; optional strategy rule merge."""
    cfg = load_sts2_config()
    if not cfg.get("auto_curate_knowledge", True):
        return {"skipped": True, "reason": "disabled"}

    limit = max_items
    if limit is None:
        try:
            limit = int(cfg.get("max_wiki_per_step", 3))
        except (TypeError, ValueError):
            limit = 3

    unknowns = collect_unknown_items(state)[: max(0, limit)]
    if not unknowns:
        return {"curated": 0, "rules_added": []}

    if use_llm is None:
        use_llm = bool(cfg.get("knowledge_use_llm", True))

    rules_added: list[str] = []
    curated = 0
    for kind, cid, name in unknowns:
        entry, rule = fetch_and_store(kind, cid, query=name, use_llm=bool(use_llm))
        if not entry:
            continue
        curated += 1
        if rule and merge_rules and rule not in rules_added:
            merge_strategy_rules([rule])
            rules_added.append(rule)

    if curated:
        _bust_memory_cache()

    return {"curated": curated, "rules_added": rules_added, "examined": len(unknowns)}


def _bust_memory_cache() -> None:
    try:
        from plugins.sts2 import memory_bus

        memory_bus._CACHE = []
        memory_bus._CACHE_TS = 0.0
    except Exception:
        pass
