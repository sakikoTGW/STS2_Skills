"""STS2 combat mechanics knowledge base (wiki.gg-sourced, bundled JSON + optional user cache)."""

from plugins.sts2.mechanics_kb.brief import format_combat_mechanics_brief
from plugins.sts2.mechanics_kb.damage_engine import (
    DamageBreakdown,
    compute_attack_damage,
    compute_block_from_card,
)
from plugins.sts2.mechanics_kb.store import (
    get_power_entry,
    load_catalog,
    lookup_wiki_examples,
    power_match_index,
)

__all__ = [
    "DamageBreakdown",
    "compute_attack_damage",
    "compute_block_from_card",
    "format_combat_mechanics_brief",
    "get_power_entry",
    "load_catalog",
    "lookup_wiki_examples",
    "power_match_index",
]
