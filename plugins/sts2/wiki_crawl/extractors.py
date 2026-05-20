"""Parse slaythespire.wiki.gg wikitext into structured facts."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def _strip(line: str) -> str:
    line = re.sub(r"\{\{[^}]+\}\}", "", line)
    line = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", line)
    line = re.sub(r"'''+?", "", line)
    return line.strip()


def extract_price_ranges(wikitext: str) -> Dict[str, List[int]]:
    """*'''Common''': 48-53 Gold → common: [48, 53]."""
    out: Dict[str, List[int]] = {}
    key_map = {
        "common": "card_common",
        "uncommon": "card_uncommon",
        "rare": "card_rare",
        "shop relic": "relic_shop",
        "shop": "relic_shop",
    }
    for line in wikitext.split("\n"):
        if "gold" not in line.lower():
            continue
        clean = _strip(line)
        m = re.search(
            r"([A-Za-z][A-Za-z ]{2,30}?)\s*:\s*(\d+)\s*[-–]\s*(\d+)\s*Gold",
            clean,
            re.I,
        )
        if not m:
            continue
        label = m.group(1).strip().lower()
        lo, hi = int(m.group(2)), int(m.group(3))
        for frag, key in sorted(key_map.items(), key=lambda x: -len(x[0])):
            if frag in label:
                out[key] = [lo, hi]
                break
        if "colorless" in label and "uncommon" in label:
            out["colorless_uncommon"] = [lo, hi]
        elif "colorless" in label and "rare" in label:
            out["colorless_rare"] = [lo, hi]
        elif "potion" in label and "common" in label:
            out["potion_common"] = [lo, hi]
        elif "potion" in label and "uncommon" in label:
            out["potion_uncommon"] = [lo, hi]
        elif "potion" in label and "rare" in label:
            out["potion_rare"] = [lo, hi]
        elif "relic" in label and "common" in label:
            out["relic_common"] = [lo, hi]
        elif "relic" in label and "uncommon" in label:
            out["relic_uncommon"] = [lo, hi]
        elif "relic" in label and "rare" in label:
            out["relic_rare"] = [lo, hi]
    return out


def extract_weight_percents(wikitext: str) -> Dict[str, float]:
    """* '''Common Potion:''' 65%"""
    out: Dict[str, float] = {}
    for line in wikitext.split("\n"):
        if "%" not in line:
            continue
        clean = _strip(line)
        m = re.search(r"([A-Za-z][A-Za-z ]+?):\s*(\d+)%", clean)
        if not m:
            continue
        label = m.group(1).strip().lower()
        val = float(m.group(2)) / 100.0
        if "potion" in label:
            if "common" in label:
                out["potion_common"] = val
            elif "uncommon" in label:
                out["potion_uncommon"] = val
            elif "rare" in label:
                out["potion_rare"] = val
        elif "relic" in label:
            if "common" in label:
                out["relic_common"] = val
            elif "uncommon" in label:
                out["relic_uncommon"] = val
            elif "rare" in label:
                out["relic_rare"] = val
    return out


def extract_card_removal(wikitext: str) -> Dict[str, Any]:
    """Card Removal Service paragraph."""
    out: Dict[str, Any] = {}
    m = re.search(
        r"price starts at (\d+).*?\{\{Asc\|6\|(\d+)",
        wikitext,
        re.S | re.I,
    )
    if m:
        out["base_cost"] = int(m.group(1))
        out["ascension_6_base_cost"] = int(m.group(2))
    m2 = re.search(
        r"increases by (\d+).*?\{\{Asc\|6\|(\d+)",
        wikitext,
        re.S | re.I,
    )
    if m2:
        out["increment_per_purchase"] = int(m2.group(1))
        out["ascension_6_increment"] = int(m2.group(2))
    if "once per Shop" in wikitext or "once per shop" in wikitext.lower():
        out["once_per_shop"] = True
    if "Eternal" in wikitext:
        out["cannot_remove_eternal"] = True
    return out


def extract_relic_blacklist(wikitext: str) -> List[str]:
    ids: List[str] = []
    for m in re.finditer(r"\{\{R\|([^|]+)\|\|2\}\}", wikitext):
        name = m.group(1).strip()
        if name and name not in ids:
            ids.append(name.upper().replace(" ", "_"))
    # only blacklist section
    blk = re.search(
        r"blacklisted from appearing in the shop:(.*?)(?:\n==|\Z)",
        wikitext,
        re.S | re.I,
    )
    if not blk:
        return []
    section_ids: List[str] = []
    for m in re.finditer(r"\{\{R\|([^|]+)\|\|2\}\}", blk.group(1)):
        rid = m.group(1).strip().upper().replace(" ", "_")
        if rid not in section_ids:
            section_ids.append(rid)
    return section_ids


def extract_act_entity_pools(wikitext: str, entity_label: str) -> Dict[str, List[str]]:
    """Parse == Act N Elites/Bosses == blocks for link=Slay_the_Spire_2:Name."""
    pools: Dict[str, List[str]] = {}
    pattern = rf"== Act (\d+) {re.escape(entity_label)} ==(.*?)(?=\n== Act |\n== [^=]|\Z)"
    for m in re.finditer(pattern, wikitext, re.S):
        act = m.group(1)
        names = re.findall(r"link=Slay_the_Spire_2:([^|\]]+)", m.group(2))
        pools[act] = [n.replace("_", " ") for n in names]
    return pools


def _split_act1_regions(names: List[str]) -> Dict[str, List[str]]:
    if len(names) >= 6:
        return {"Overgrowth": names[:3], "Underdocks": names[3:6]}
    if len(names) >= 3:
        return {"Overgrowth": names[:3]}
    return {}


def extract_elite_pools(wikitext: str) -> Dict[str, Any]:
    """Act elite names from == Act N Elites == sections."""
    rewards: Dict[str, Any] = {}
    gm = re.search(r"(\d+)-(\d+)\s*\(\{\{Asc\|3\|(\d+)-(\d+)", wikitext)
    if gm:
        rewards["gold_range"] = [int(gm.group(1)), int(gm.group(2))]
        rewards["gold_range_ascension_3"] = [int(gm.group(3)), int(gm.group(4))]
    rewards["drops"] = ["relic", "gold", "card_reward"]

    pools = extract_act_entity_pools(wikitext, "Elites")
    rules = []
    if "cannot be encountered twice in a row" in wikitext:
        rules.append("same_elite_not_twice_in_a_row")
    if "all 3 different Elites" in wikitext:
        rules.append("must_see_all_three_before_repeat")
    out: Dict[str, Any] = {"rewards": rewards, "act_pools": pools, "spawn_rules": rules}
    if pools.get("1"):
        out["act1_by_region"] = _split_act1_regions(pools["1"])
    return out


def parse_bosses_page(wikitext: str) -> Dict[str, Any]:
    pools = extract_act_entity_pools(wikitext, "Bosses")
    rewards: Dict[str, Any] = {"drops": ["gold", "rare_card_choice", "potion_maybe"]}
    gm = re.search(
        r"rewarded with (\d+) \(\{\{Asc\|3\|(\d+)",
        wikitext,
    )
    if gm:
        rewards["gold"] = [int(gm.group(1)), int(gm.group(1))]
        rewards["gold_ascension_3"] = [int(gm.group(2)), int(gm.group(2))]
    heal = re.search(
        r"heals the player for (\d+)% \(\{\{Asc\|2\|(\d+)%",
        wikitext,
    )
    if heal:
        rewards["post_boss_ancient_heal_ratio"] = float(heal.group(1)) / 100.0
        rewards["post_boss_ancient_heal_ratio_ascension_2"] = float(heal.group(2)) / 100.0
    relics = []
    for m in re.finditer(r"\{\{R\|([^|]+)\|\|2\}\}.*?(?:Boss|Pantograph|Stone Cracker|Lava Rock)", wikitext):
        relics.append(m.group(1).strip().upper().replace(" ", "_"))
    out: Dict[str, Any] = {
        "wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:Bosses",
        "act_pools": pools,
        "rewards": rewards,
        "spawn_rules": [
            "floor_before_boss_is_rest_site",
            "ascension_10_act3_double_boss_no_rest_between",
        ],
        "boss_relic_synergies": list(dict.fromkeys(relics))[:8],
    }
    if pools.get("1"):
        out["act1_by_region"] = _split_act1_regions(pools["1"])
    return out


def parse_events_page(wikitext: str) -> Dict[str, Any]:
    mp: List[str] = []
    blk = re.search(r"=== Multiplayer Events ===(.*?)(?:\n==|\Z)", wikitext, re.S)
    if blk:
        for m in re.finditer(r"\{\{E\|([^|]+)\|\|2\}\}", blk.group(1)):
            mp.append(m.group(1).strip())
    return {
        "wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:Events",
        "only_on_unknown_nodes": True,
        "must_choose_option": True,
        "lethal_option_red_outline": True,
        "grey_out_unavailable": True,
        "multiplayer_collaborative_events": mp,
        "event_types": ["combat_event", "quest"],
        "agent_hints": [
            "事件只在「未知」节点；必须选一项才能离开",
            "致死选项红框仍可点（蜥蜴尾巴等）",
            "联机部分事件需全员同选",
        ],
    }


def parse_treasure_from_map(wikitext: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:Map_Locations#Treasure_Room",
    }
    gm = re.search(
        r"(\d+)-(\d+) \(\{\{Asc\|3\|(\d+)-(\d+)",
        wikitext,
    )
    if gm:
        out["gold_range"] = [int(gm.group(1)), int(gm.group(2))]
        out["gold_range_ascension_3"] = [int(gm.group(3)), int(gm.group(4))]
    if "guaranteed at the halfway" in wikitext.lower():
        out["guaranteed_mid_act"] = True
    out["default_drops"] = ["relic"]
    return out


def parse_potions_page(wikitext: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:Potions",
        "default_slots": 3,
        "ascension_4_slots": 2,
        "no_energy_cost": True,
        "not_a_card_play": True,
    }
    m = re.search(r"default chance.*?(\d+)%", wikitext, re.I | re.S)
    if m:
        out["combat_drop_chance"] = float(m.group(1)) / 100.0
    rarity = {}
    for label, key in (
        ("Common Potion", "common"),
        ("Uncommon Potion", "uncommon"),
        ("Rare Potion", "rare"),
    ):
        rm = re.search(rf"{label}\s*\n\|(\d+)%", wikitext)
        if rm:
            rarity[key] = float(rm.group(1)) / 100.0
    if rarity:
        out["rarity_weights"] = rarity
    return out


def parse_relic_catalog(wikitext: str) -> Dict[str, Any]:
    starters: Dict[str, Dict[str, str]] = {}
    for m in re.finditer(
        r"\|\s*(Ironclad|Silent|Regent|Necrobinder|Defect)\s*\n\|\{\{R\|([^|]+)\|\|2\}\}\s*\n\|\{\{R\|([^|]+)\|\|2\}\}",
        wikitext,
    ):
        starters[m.group(1).lower()] = {
            "starter": m.group(2).strip().upper().replace(" ", "_"),
            "ancient_upgrade": m.group(3).strip().upper().replace(" ", "_"),
        }
    return {
        "wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:Relics",
        "starter_relics": starters,
        "sources": [
            "elites",
            "chests",
            "merchant",
            "shovel_at_rest",
            "ancients",
            "events",
        ],
        "shop_relic_count": 30,
        "shop_relic_right_slot": True,
        "event_relics_exclusive": True,
        "circlet_special": True,
        "agent_hints": [
            "遗物整局唯一（圆环例外）",
            "商店遗物仅商人；右槽必为商店遗物",
            "先古遗物每幕初；事件遗物仅事件",
        ],
    }


def parse_neow_page(wikitext: str) -> Dict[str, Any]:
    curse: List[Dict[str, str]] = []
    positive: List[Dict[str, str]] = []
    pool = None
    for line in wikitext.split("\n"):
        if "=== Curse Pool ===" in line:
            pool = "curse"
            continue
        if "=== Positive Pool ===" in line:
            pool = "positive"
            continue
        if line.startswith("===") and "Pool" in line:
            pool = None
        m = re.search(r"\{\{R\|([^|]+)\|\|2\}\}\|\|(.+)", line)
        if m and pool:
            ent = {
                "id": m.group(1).strip().upper().replace(" ", "_"),
                "effect": _strip(m.group(2))[:200],
            }
            (curse if pool == "curse" else positive).append(ent)
    return {
        "wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:Neow",
        "curse_pool": curse,
        "positive_pool": positive,
        "pick_rules": [
            "先定诅咒池1件，再调正面池",
            "最终三选一：1诅咒遗物+2正面遗物",
        ],
        "agent_hints": [
            "开局涅奥：三选一，含负面池遗物",
            "银坩埚：前3次卡牌奖励升级、首个宝箱空",
        ],
    }


def extract_power_damage_multiplier(wikitext: str, power_name: str) -> Optional[float]:
    """e.g. Vulnerable: increased by 50% → 1.5"""
    patterns = [
        rf"{re.escape(power_name)}.*?(\d+)%\s+more",
        rf"increased by (\d+)%",
        rf"decreased by (\d+)%",
    ]
    low = wikitext.lower()
    for pat in patterns:
        m = re.search(pat, wikitext, re.I | re.S)
        if m:
            pct = int(m.group(1))
            if "decreased" in (m.group(0).lower() if m.lastindex else ""):
                return 1.0 - pct / 100.0
            if "more" in low or "increased" in (m.group(0).lower()):
                return 1.0 + pct / 100.0
    if "decreased by 25%" in low and power_name.lower() in ("weak",):
        return 0.75
    if "decreased by 25%" in low and "frail" in low:
        return 0.75
    return None


def parse_merchant_page(wikitext: str) -> Dict[str, Any]:
    removal = extract_card_removal(wikitext)
    return {
        "wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:The_Merchant",
        "inventory": {
            "colored_cards": {
                "count": 5,
                "composition": "2 Attack, 2 Skill, 1 Power (current character)",
                "one_random_50pct_discount": True,
            },
            "colorless_cards": {"count": 2, "premium_pct": 15},
            "potions": {"count": 3},
            "relics": {
                "count": 3,
                "right_slot_always_shop_relic": True,
            },
        },
        "prices": extract_price_ranges(wikitext),
        "weights": extract_weight_percents(wikitext),
        "card_removal": removal,
        "shop_relic_blacklist": extract_relic_blacklist(wikitext),
        "relic_interactions": _merchant_relic_interactions(wikitext),
    }


def _merchant_relic_interactions(wikitext: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if "Membership Card" in wikitext:
        items.append({"id": "MEMBERSHIP_CARD", "effect": "all_prices_multiplier", "value": 0.5})
    if "The Courier" in wikitext:
        items.append(
            {
                "id": "THE_COURIER",
                "effect": "price_multiplier_and_restock",
                "value": 0.8,
                "restocks": ["cards", "relics", "potions"],
                "no_restock_shop_relic": True,
            }
        )
    if "0.5 * 0.8 = 0.4" in wikitext:
        items.append(
            {
                "ids": ["MEMBERSHIP_CARD", "THE_COURIER"],
                "effect": "combined_price_multiplier",
                "value": 0.4,
            }
        )
    if "Meal Ticket" in wikitext:
        items.append({"id": "MEAL_TICKET", "effect": "heal_on_enter_shop", "value": 15})
    if "Lord's Parasol" in wikitext:
        items.append({"id": "LORDS_PARASOL", "effect": "auto_buy_all_on_enter"})
    return items


def parse_elites_page(wikitext: str) -> Dict[str, Any]:
    base = extract_elite_pools(wikitext)
    return {"wiki": "https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:Elites", **base}
