"""Map game state → crawled wiki facts."""

from __future__ import annotations

from typing import Any

from plugins.sts2.wiki_crawl.crawler import load_crawled_index, load_page_facts

# state_type / signals → wiki page titles
_SCREEN_PAGES: dict[str, list[str]] = {
    "rest_site": [
        "Slay_the_Spire_2:Rest_Sites",
        "Slay_the_Spire_2:Ascension",
        "Slay_the_Spire_2:Potions",
    ],
    "shop": ["Slay_the_Spire_2:The_Merchant", "Slay_the_Spire_2:Gold"],
    "merchant": ["Slay_the_Spire_2:The_Merchant", "Slay_the_Spire_2:Gold"],
    "fake_merchant": ["Slay_the_Spire_2:The_Merchant"],
    "map": ["Slay_the_Spire_2:Map_Locations", "Slay_the_Spire_2:Acts"],
    "card_reward": ["Slay_the_Spire_2:Rewards", "Slay_the_Spire_2:Upgrade"],
    "card_select": ["Slay_the_Spire_2:Rewards"],
    "rewards": ["Slay_the_Spire_2:Rewards"],
    "event": ["Slay_the_Spire_2:Events"],
    "boss": ["Slay_the_Spire_2:Bosses"],
    "elite": ["Slay_the_Spire_2:Elites"],
    "treasure": ["Slay_the_Spire_2:Map_Locations", "Slay_the_Spire_2:Relics"],
    "relic_select": ["Slay_the_Spire_2:Relics"],
    "relic_select_boss": ["Slay_the_Spire_2:Relics", "Slay_the_Spire_2:Bosses"],
}

_POWER_PAGES: dict[str, str] = {
    "vulnerable": "Slay_the_Spire_2:Vulnerable",
    "weak": "Slay_the_Spire_2:Weak",
    "frail": "Slay_the_Spire_2:Frail",
    "strength": "Slay_the_Spire_2:Strength",
    "dexterity": "Slay_the_Spire_2:Dexterity",
    "poison": "Slay_the_Spire_2:Poison",
    "artifact": "Slay_the_Spire_2:Artifact",
    "intangible": "Slay_the_Spire_2:Intangible",
    "hang": "Slay_the_Spire_2:Hang",
    "slow": "Slay_the_Spire_2:Slow",
    "focus": "Slay_the_Spire_2:Focus",
}


def _normalize_power_id(raw: str) -> str:
    return raw.lower().replace(" ", "_").split(":")[-1]


def _powers_on_battlefield(state: dict) -> set[str]:
    ids: set[str] = set()
    battle = state.get("battle") or {}
    for side in ("player", "enemies"):
        if side == "player":
            units = [battle.get("player") or state.get("player") or {}]
        else:
            units = battle.get("enemies") or []
        for u in units:
            if not u:
                continue
            for p in (u.get("powers") or u.get("buffs") or []):
                if isinstance(p, dict):
                    pid = p.get("id") or p.get("power_id") or p.get("name") or ""
                else:
                    pid = str(p)
                if pid:
                    ids.add(_normalize_power_id(str(pid)))
    return ids


def pages_for_state(state: dict) -> list[str]:
    st = str(state.get("state_type") or "")
    pages: list[str] = []

    if st in _SCREEN_PAGES:
        pages.extend(_SCREEN_PAGES[st])

    if st in ("monster", "elite", "boss", "hand_select"):
        pages.append("Slay_the_Spire_2:Block")
        pages.append("Slay_the_Spire_2:Debuffs")
        for pid in sorted(_powers_on_battlefield(state)):
            wiki = _POWER_PAGES.get(pid)
            if wiki and wiki not in pages:
                pages.append(wiki)

    ev = state.get("event") or {}
    name = str(ev.get("event_name") or ev.get("event_id") or "").lower()
    if any(x in name for x in ("neow", "涅奥", "ancient", "先古")):
        pages.extend(
            [
                "Slay_the_Spire_2:Neow",
                "Slay_the_Spire_2:Ancients",
            ]
        )

    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for p in pages:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def format_wiki_facts_block(state: dict, *, max_pages: int = 4) -> str:
    idx = load_crawled_index()
    if not (idx.get("pages")):
        return ""

    titles = pages_for_state(state)[:max_pages]
    if not titles:
        return ""

    lines = ["【Wiki 摘要·wiki.gg 爬取】"]
    for title in titles:
        facts = load_page_facts(title)
        if not facts:
            continue
        short = facts.get("short_name") or title.split(":")[-1]
        summary = (facts.get("summary") or "").strip()
        if not summary:
            continue
        if len(summary) > 380:
            summary = summary[:377] + "…"
        lines.append(f"  · {short}: {summary}")
        secs = facts.get("sections") or {}
        for sec_name, bullets in list(secs.items())[:1]:
            if bullets:
                lines.append(f"    {sec_name}: {bullets[0][:120]}")
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def wiki_facts_for_state(state: dict) -> dict[str, Any]:
    """Structured slice for logging / tools."""
    out: dict[str, Any] = {"pages": []}
    for title in pages_for_state(state):
        facts = load_page_facts(title)
        if facts:
            out["pages"].append(
                {
                    "title": title,
                    "summary": (facts.get("summary") or "")[:500],
                }
            )
    return out
