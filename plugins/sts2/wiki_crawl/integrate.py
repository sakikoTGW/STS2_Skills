"""Merge wiki crawl into game_flow_kb + mechanics_kb bundled JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from plugins.sts2.wiki_crawl.crawler import bundled_dir as crawl_bundled_dir
from plugins.sts2.wiki_crawl.crawler import load_page_facts
from plugins.sts2.wiki_crawl.crawler import user_dir as crawl_user_dir
from plugins.sts2.wiki_crawl.extractors import (
    extract_power_damage_multiplier,
    parse_bosses_page,
    parse_elites_page,
    parse_events_page,
    parse_merchant_page,
    parse_neow_page,
    parse_potions_page,
    parse_relic_catalog,
    parse_treasure_from_map,
)

logger = logging.getLogger(__name__)

_GAME_FLOW_ROOT = (
    Path(__file__).resolve().parents[1] / "references" / "game_flow_kb"
)
_MECH_ROOT = Path(__file__).resolve().parents[1] / "references" / "mechanics_kb"

_POWER_WIKI_PAGES = {
    "VULNERABLE": ("Slay_the_Spire_2:Vulnerable", "Vulnerable", "damage_multiplier", 1.5),
    "WEAK": ("Slay_the_Spire_2:Weak", "Weak", "damage_multiplier", 0.75),
    "FRAIL": ("Slay_the_Spire_2:Frail", "Frail", "block_multiplier", 0.75),
}

_CORE_CARDS = {
    "STRIKE": {"damage": [6, 9], "type": "attack", "wiki": "Slay_the_Spire_2:Strike"},
    "DEFEND": {"block": [5, 8], "type": "skill", "wiki": "Slay_the_Spire_2:Defend"},
    "BASH": {"damage": [8, 10], "vulnerable_turns": [2, 3], "wiki": "Slay_the_Spire_2:Bash"},
    "BLUDGEON": {"damage": [32, 42], "wiki": "Slay_the_Spire_2:Bludgeon"},
    "TWIN_STRIKE": {"damage": [5, 7], "hits": 2, "wiki": "Slay_the_Spire_2:Twin_Strike"},
    "POMMEL_STRIKE": {"damage": [9, 10], "wiki": "Slay_the_Spire_2:Pommel_Strike"},
    "SHOCKWAVE": {"vulnerable_turns": [3, 5], "weak_turns": [3, 5], "aoe": True, "wiki": "Slay_the_Spire_2:Shockwave"},
    "UPPERCUT": {"vulnerable_turns": [1, 2], "weak_turns": [1, 2], "wiki": "Slay_the_Spire_2:Uppercut"},
    "THUNDERCLAP": {"vulnerable_turns": [2, 3], "aoe": True, "wiki": "Slay_the_Spire_2:Thunderclap"},
    "DEADLY_POISON": {"poison": [5, 7], "wiki": "Slay_the_Spire_2:Deadly_Poison"},
    "NEUTRALIZE": {"weak_turns": [1, 2], "wiki": "Slay_the_Spire_2:Neutralize"},
}

_BUFF_WIKI = [
    ("STRENGTH", "Slay_the_Spire_2:Strength"),
    ("DEXTERITY", "Slay_the_Spire_2:Dexterity"),
    ("POISON", "Slay_the_Spire_2:Poison"),
]


def _fetch_wikitext(page_title: str) -> str:
    """User/bundled crawl snapshot, else live API."""
    for root in (crawl_user_dir(), crawl_bundled_dir()):
        for sub in ("wikitext", "pages"):
            fp = root / sub / f"{page_title.split(':')[-1]}.txt"
            if fp.is_file():
                return fp.read_text(encoding="utf-8")
        facts = None
        if sub == "pages":
            from plugins.sts2.wiki_crawl.crawler import load_page_facts as lpf

            facts = lpf(page_title)
        if facts and facts.get("wikitext"):
            return str(facts["wikitext"])
    try:
        from plugins.sts2.wiki_crawl.crawler import crawl_page

        facts = crawl_page(page_title, delay_sec=0.5)
        return str(facts.get("wikitext") or "")
    except Exception as exc:
        logger.warning("wikitext fetch %s: %s", page_title, exc)
        return ""


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_merchant_defaults(data: dict[str, Any]) -> dict[str, Any]:
    defaults = _default_merchant()
    for key in ("prices", "weights", "inventory", "agent_hints"):
        if not data.get(key) and defaults.get(key):
            data[key] = defaults[key]
    if not data.get("relic_interactions"):
        data["relic_interactions"] = defaults.get("relic_interactions")
    return data


def integrate_merchant(*, write: bool = True) -> dict[str, Any]:
    wt = _fetch_wikitext("Slay_the_Spire_2:The_Merchant")
    data = parse_merchant_page(wt) if wt else _default_merchant()
    data = _merge_merchant_defaults(data)
    if write:
        _write_json(_GAME_FLOW_ROOT / "merchant.json", data)
    return data


def _default_merchant() -> dict[str, Any]:
    return {
        "wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:The_Merchant",
        "prices": {
            "card_common": [48, 53],
            "card_uncommon": [71, 79],
            "card_rare": [143, 158],
            "colorless_uncommon": [82, 90],
            "colorless_rare": [164, 181],
            "potion_common": [48, 53],
            "potion_uncommon": [71, 79],
            "potion_rare": [95, 105],
            "relic_shop": [170, 230],
            "relic_common": [149, 201],
            "relic_uncommon": [191, 259],
            "relic_rare": [234, 316],
        },
        "card_removal": {
            "base_cost": 75,
            "increment_per_purchase": 25,
            "ascension_6_base_cost": 100,
            "ascension_6_increment": 50,
            "once_per_shop": True,
            "cannot_remove_eternal": True,
        },
        "shop_relic_blacklist": [
            "AMETHYST_AUBERGINE",
            "BOWLER_HAT",
            "LUCKY_FYSH",
            "OLD_COIN",
            "THE_COURIER",
        ],
        "agent_hints": [
            "删牌每店仅一次；A6 首删 100 金、之后每次 +50",
            "会员证 50% 价；送货员 80% 且补货（商店遗物槽不补）",
        ],
    }


def integrate_elites(*, write: bool = True) -> dict[str, Any]:
    wt = _fetch_wikitext("Slay_the_Spire_2:Elites")
    data = parse_elites_page(wt) if wt else {}
    if not data.get("act_pools"):
        data = _default_elites()
    if write:
        _write_json(_GAME_FLOW_ROOT / "elites.json", data)
    return data


def _default_elites() -> dict[str, Any]:
    return {
        "wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:Elites",
        "rewards": {
            "gold_range": [35, 45],
            "gold_range_ascension_3": [26, 34],
            "drops": ["relic", "gold", "card_reward"],
        },
        "act_pools": {
            "1": [
                "Bygone Effigy",
                "Byrdonis",
                "Phrog Parasite",
                "Skulking Colony",
                "Phantasmal Gardener",
                "Terror Eel",
            ],
            "2": ["Decimillipede", "Entomancer", "Infested Prism"],
            "3": ["Knights", "Mecha Knight", "Soul Nexus"],
        },
        "act1_by_region": {
            "Overgrowth": ["Bygone Effigy", "Byrdonis", "Phrog Parasite"],
            "Underdocks": ["Skulking Colony", "Phantasmal Gardener", "Terror Eel"],
        },
        "spawn_rules": [
            "must_see_all_three_before_repeat",
            "same_elite_not_twice_in_a_row",
        ],
    }


def integrate_shop_relics(*, write: bool = True) -> dict[str, Any]:
    wt = _fetch_wikitext("Slay_the_Spire_2:The_Merchant")
    merchant = parse_merchant_page(wt) if wt else _default_merchant()
    entries = list(merchant.get("relic_interactions") or [])
    data = {"wiki": merchant.get("wiki"), "entries": entries}
    if write:
        _write_json(_MECH_ROOT / "modifiers" / "shop_relics.json", data)
    return data


def integrate_core_cards(*, write: bool = True) -> dict[str, Any]:
    cards = dict(_CORE_CARDS)
    for cid, ent in list(cards.items()):
        wiki_page = ent.get("wiki", "")
        if not wiki_page:
            continue
        facts = load_page_facts(wiki_page)
        if facts and facts.get("summary"):
            ent["wiki_summary"] = (facts.get("summary") or "")[:300]
    data = {"description": "核心攻防牌（伤害/层数对齐 mechanics_kb 验算）", "cards": cards}
    if write:
        _write_json(_MECH_ROOT / "cards" / "core_attacks.json", data)
    return data


def _integrate_json(
    filename: str,
    parser,
    page: str,
    *,
    default: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    wt = _fetch_wikitext(page)
    data = parser(wt) if wt else dict(default or {})
    if default:
        for key, val in default.items():
            if not data.get(key):
                data[key] = val
    if write:
        _write_json(_GAME_FLOW_ROOT / filename, data)
    return data


def integrate_bosses(*, write: bool = True) -> dict[str, Any]:
    default = json.loads((_GAME_FLOW_ROOT / "bosses.json").read_text(encoding="utf-8"))
    return _integrate_json(
        "bosses.json",
        parse_bosses_page,
        "Slay_the_Spire_2:Bosses",
        default=default,
        write=write,
    )


def integrate_events(*, write: bool = True) -> dict[str, Any]:
    default = json.loads((_GAME_FLOW_ROOT / "events.json").read_text(encoding="utf-8"))
    return _integrate_json(
        "events.json",
        parse_events_page,
        "Slay_the_Spire_2:Events",
        default=default,
        write=write,
    )


def integrate_chests(*, write: bool = True) -> dict[str, Any]:
    default = json.loads((_GAME_FLOW_ROOT / "chests.json").read_text(encoding="utf-8"))

    def _parse(wt: str) -> dict[str, Any]:
        d = parse_treasure_from_map(wt)
        d["agent_hints"] = default.get("agent_hints")
        return d

    wt = _fetch_wikitext("Slay_the_Spire_2:Map_Locations")
    data = _parse(wt) if wt else dict(default)
    if write:
        _write_json(_GAME_FLOW_ROOT / "chests.json", data)
    return data


def integrate_potions(*, write: bool = True) -> dict[str, Any]:
    default = json.loads((_GAME_FLOW_ROOT / "potions.json").read_text(encoding="utf-8"))
    return _integrate_json(
        "potions.json",
        parse_potions_page,
        "Slay_the_Spire_2:Potions",
        default=default,
        write=write,
    )


def integrate_relic_catalog(*, write: bool = True) -> dict[str, Any]:
    default = json.loads(
        (_GAME_FLOW_ROOT / "relic_catalog.json").read_text(encoding="utf-8")
    )
    return _integrate_json(
        "relic_catalog.json",
        parse_relic_catalog,
        "Slay_the_Spire_2:Relics",
        default=default,
        write=write,
    )


def integrate_neow(*, write: bool = True) -> dict[str, Any]:
    default = json.loads((_GAME_FLOW_ROOT / "neow.json").read_text(encoding="utf-8"))
    wt = _fetch_wikitext("Slay_the_Spire_2:Neow")
    data = parse_neow_page(wt) if wt else dict(default)
    if not data.get("curse_pool"):
        data["curse_pool"] = default.get("curse_pool")
    if not data.get("positive_pool"):
        data["positive_pool"] = default.get("positive_pool")
    if write:
        _write_json(_GAME_FLOW_ROOT / "neow.json", data)
    return data


def integrate_buffs_from_wiki(*, write: bool = True) -> dict[str, Any]:
    buffs_path = _MECH_ROOT / "powers" / "buffs.json"
    raw = json.loads(buffs_path.read_text(encoding="utf-8"))
    enriched = []
    for ent in raw.get("entries") or []:
        pid = str(ent.get("id") or "")
        page = next((p for i, p in _BUFF_WIKI if i == pid), None)
        if not page:
            continue
        facts = load_page_facts(page)
        if facts and facts.get("summary"):
            ent["wiki_summary"] = (facts.get("summary") or "")[:400]
            enriched.append(pid)
    if write:
        _write_json(buffs_path, raw)
    return {"enriched": enriched}


def integrate_powers_from_wiki(*, write: bool = True) -> dict[str, Any]:
    """Enrich debuffs.json with wiki_summary; verify multipliers."""
    debuffs_path = _MECH_ROOT / "powers" / "debuffs.json"
    raw = json.loads(debuffs_path.read_text(encoding="utf-8"))
    report: dict[str, Any] = {"verified": [], "skipped": [], "enriched": []}
    for ent in raw.get("entries") or []:
        pid = str(ent.get("id") or "")
        spec = _POWER_WIKI_PAGES.get(pid)
        if not spec:
            continue
        page, name, field, expected = spec
        wt = _fetch_wikitext(page)
        facts = load_page_facts(page)
        if facts and facts.get("summary"):
            ent["wiki_summary"] = (facts.get("summary") or "")[:400]
            report["enriched"].append(pid)
        mult = extract_power_damage_multiplier(wt, name) if wt else None
        if mult is not None and field in ent:
            actual = float(ent.get(field) or 0)
            if abs(actual - mult) > 0.01 and abs(actual - expected) < 0.01:
                report["verified"].append({"id": pid, "field": field, "value": actual})
            elif abs(actual - expected) > 0.01:
                report["skipped"].append(
                    {
                        "id": pid,
                        "reason": f"kb={actual} wiki≈{mult} expected={expected}",
                    }
                )
    if write:
        _write_json(debuffs_path, raw)
    return report


def update_catalogs() -> None:
    gf = _GAME_FLOW_ROOT / "catalog.json"
    cat = json.loads(gf.read_text(encoding="utf-8"))
    files = list(cat.get("entry_files") or [])
    for rel in (
        "merchant.json",
        "elites.json",
        "bosses.json",
        "events.json",
        "chests.json",
        "potions.json",
        "relic_catalog.json",
        "neow.json",
        "rewards.json",
        "events_catalog.json",
    ):
        if rel not in files:
            files.append(rel)
    cat["entry_files"] = files
    if int(cat.get("version", 0)) < 6:
        cat["version"] = 6
    _write_json(gf, cat)

    mc = _MECH_ROOT / "catalog.json"
    mcat = json.loads(mc.read_text(encoding="utf-8"))
    mfiles = list(mcat.get("entry_files") or [])
    for rel in ("cards/core_attacks.json", "modifiers/shop_relics.json", "relics_index.json"):
        if rel not in mfiles:
            mfiles.append(rel)
    if int(mcat.get("version", 0)) < 5:
        mcat["version"] = 5
    mcat["entry_files"] = mfiles
    _write_json(mc, mcat)


def integrate_catalogs(
    *,
    write: bool = True,
    max_events: int | None = None,
    max_relics: int | None = None,
    crawl_missing: bool = True,
) -> dict[str, Any]:
    from plugins.sts2.wiki_crawl.list_index import (
        build_events_catalog,
        build_relics_index,
        write_catalogs,
    )

    ev_path = _GAME_FLOW_ROOT / "events_catalog.json"
    rel_path = _MECH_ROOT / "relics_index.json"

    if max_events == 0:
        events = (
            json.loads(ev_path.read_text(encoding="utf-8"))
            if ev_path.is_file()
            else {"count": 0, "entries": {}, "errors": []}
        )
    else:
        events = build_events_catalog(max_pages=max_events, crawl_missing=crawl_missing)
        if ev_path.is_file() and crawl_missing is False:
            prev = json.loads(ev_path.read_text(encoding="utf-8"))
            merged = dict(prev.get("entries") or {})
            merged.update(events.get("entries") or {})
            events["entries"] = merged
            events["count"] = len(merged)

    if max_relics == 0:
        relics = (
            json.loads(rel_path.read_text(encoding="utf-8"))
            if rel_path.is_file()
            else {"count": 0, "entries": {}, "errors": [], "by_rarity": {}}
        )
    else:
        relics = build_relics_index(max_pages=max_relics, crawl_missing=crawl_missing)
        if rel_path.is_file() and crawl_missing is False:
            prev = json.loads(rel_path.read_text(encoding="utf-8"))
            merged = dict(prev.get("entries") or {})
            merged.update(relics.get("entries") or {})
            relics["entries"] = merged
            relics["count"] = len(merged)
    if write:
        write_catalogs(events, relics, game_flow_root=_GAME_FLOW_ROOT, mech_root=_MECH_ROOT)
    return {
        "events_count": events.get("count"),
        "events_errors": events.get("errors_count", len(events.get("errors") or [])),
        "relics_count": relics.get("count"),
        "relics_errors": relics.get("errors_count", len(relics.get("errors") or [])),
        "relics_by_rarity": relics.get("by_rarity"),
    }


def integrate_all(*, write: bool = True) -> dict[str, Any]:
    out = {
        "merchant": integrate_merchant(write=write),
        "elites": integrate_elites(write=write),
        "bosses": integrate_bosses(write=write),
        "events": integrate_events(write=write),
        "chests": integrate_chests(write=write),
        "potions": integrate_potions(write=write),
        "relic_catalog": integrate_relic_catalog(write=write),
        "neow": integrate_neow(write=write),
        "shop_relics": integrate_shop_relics(write=write),
        "core_cards": integrate_core_cards(write=write),
        "powers": integrate_powers_from_wiki(write=write),
        "buffs": integrate_buffs_from_wiki(write=write),
        "catalogs": integrate_catalogs(write=write, crawl_missing=True),
    }
    if write:
        update_catalogs()
    return out
