"""Enemy wiki resolution — normalize IDs, fetch STS2 MCP wiki, surface to agent."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

_SUFFIX_NUM = re.compile(r"_(\d+)$")


def normalize_enemy_wiki_id(enemy: dict) -> str:
    """Map battle entity_id PHANTASMAL_GARDENER_2 → PHANTASMAL_GARDENER for wiki."""
    if not isinstance(enemy, dict):
        return ""
    for key in ("id", "enemy_id", "monster_id"):
        raw = str(enemy.get(key) or "").strip().upper()
        if raw:
            return _SUFFIX_NUM.sub("", raw)
    ent = str(enemy.get("entity_id") or "").strip().upper()
    if not ent:
        return ""
    return _SUFFIX_NUM.sub("", ent)


def enemy_display_name(enemy: dict) -> str:
    return str(enemy.get("name") or enemy.get("id") or normalize_enemy_wiki_id(enemy) or "?")


def enemy_powers_blob(enemy: dict) -> str:
    parts: List[str] = []
    for p in enemy.get("powers") or []:
        if not isinstance(p, dict):
            continue
        parts.append(
            " ".join(
                str(p.get(k) or "")
                for k in ("name", "id", "description", "amount", "stacks")
            )
        )
    return " ".join(parts)


def fetch_enemy_wiki(enemy: dict, *, use_llm: bool = False) -> Tuple[dict | None, str]:
    """Fetch wiki entry for one enemy. Returns (entry, wiki_key)."""
    wiki_key = normalize_enemy_wiki_id(enemy)
    if not wiki_key:
        return None, ""
    name = enemy_display_name(enemy)
    query = name if name and name != wiki_key else wiki_key.replace("_", " ")
    from plugins.sts2.knowledge import fetch_and_store

    ent, rule = fetch_and_store("enemies", wiki_key, query=query, use_llm=use_llm)
    return ent, wiki_key


def _format_kb_intents(ent: dict) -> str:
    intents = ent.get("intents") or []
    if not intents:
        return ""
    parts: List[str] = []
    for it in intents[:6]:
        if not isinstance(it, dict):
            continue
        nm = it.get("name") or "?"
        tp = it.get("type") or "?"
        extra = ""
        if it.get("damage"):
            extra += f"{it['damage']}伤"
        if it.get("hits"):
            extra += f"x{it['hits']}"
        if it.get("effect"):
            extra += str(it["effect"])
        parts.append(f"{nm}({tp}{extra})")
    return "意图表:" + "、".join(parts)


def format_enemy_wiki_lines(state: dict) -> str:
    """【怪物Wiki】block — huiji 本地库优先，再 MCP wiki API。"""
    enemies = (state.get("battle") or {}).get("enemies") or []
    if not enemies:
        return ""

    from plugins.sts2.config import load_sts2_config
    from plugins.sts2.huiji_kb.store import kb_stats, lookup_enemy

    cfg = load_sts2_config()
    use_llm = bool(cfg.get("knowledge_use_llm", False))
    try:
        from plugins.sts2.play_mode import agent_play_mode

        budget = int(cfg.get("study_combat_wiki_max_fetches", 4))
        if agent_play_mode():
            budget = max(budget, int(cfg.get("agent_combat_wiki_max_fetches", 12)))
    except Exception:
        budget = 4

    stats = kb_stats()
    lines: List[str] = [
        f"【怪物Wiki·本地库{stats['merged']}条+游戏API，禁止臆测机制】",
        "  每只怪以本块为准；缺条目: sts2_wiki_search(item_type=enemy)。全量同步: hermes sts2 sync-wiki",
    ]
    spent = 0
    for e in enemies:
        if not isinstance(e, dict):
            continue
        if int(e.get("hp", 0) or 0) <= 0:
            continue
        wiki_key = normalize_enemy_wiki_id(e)
        name = enemy_display_name(e)
        intents = e.get("intents") or []
        it0 = ""
        if intents and isinstance(intents[0], dict):
            it = intents[0]
            it0 = f" T+0:{it.get('type','?')}/{it.get('label','?')}"
        powers = enemy_powers_blob(e).strip()
        head = f"  · {name} key={wiki_key} HP={e.get('hp','?')}{it0}"
        if powers:
            head += f"\n    状态: {powers[:160]}"

        huiji = lookup_enemy(wiki_key)
        ent = None
        if huiji:
            from plugins.sts2.huiji_kb.loops import forecast_enemy, format_loop_forecast

            rule = str(huiji.get("rule") or huiji.get("combat_plan") or "").strip()
            block = [head]
            if huiji.get("hp_solo"):
                block.append(f"    WikiHP(单人): {huiji['hp_solo']}")
            fc = forecast_enemy(huiji, e, horizon=3)
            loop_line = format_loop_forecast(fc)
            if loop_line:
                block.append(f"    {loop_line[:280]}")
            elif not (huiji.get("behavior_loop") or {}).get("steps"):
                block.append(
                    "    ⚠ 无 behavior_loop — T+1 勿写「推测攻击」；补 loops_act1 或 sync-wiki"
                )
            it_line = _format_kb_intents(huiji)
            if it_line and not loop_line:
                block.append(f"    {it_line[:220]}")
            if huiji.get("combat_plan"):
                block.append(f"    对策: {str(huiji['combat_plan'])[:200]}")
            elif rule:
                block.append(f"    Wiki规则: {rule[:220]}")
            for pw in huiji.get("powers") or []:
                block.append(f"    机制: {str(pw)[:160]}")
            lines.append("\n".join(block))
            continue

        if spent < budget:
            ent, _ = fetch_enemy_wiki(e, use_llm=use_llm)
            spent += 1

        if ent:
            rule = str(ent.get("rule") or "").strip()
            snippet = str(ent.get("wiki_snippet") or ent.get("description") or "").strip()
            if rule:
                lines.append(head + f"\n    Wiki规则: {rule[:280]}")
            elif snippet:
                lines.append(head + f"\n    Wiki: {snippet[:280]}")
            else:
                lines.append(head)
        else:
            lines.append(head + "\n    (Wiki 未命中 — 请 sts2_wiki_search 或 hermes sts2 sync-wiki)")
    return "\n".join(lines)


def prefetch_battle_wiki(state: dict) -> List[str]:
    """Eager fetch for all enemies; returns wiki keys fetched."""
    keys: List[str] = []
    for e in (state.get("battle") or {}).get("enemies") or []:
        if int((e or {}).get("hp", 0) or 0) <= 0:
            continue
        ent, k = fetch_enemy_wiki(e, use_llm=False)
        if ent and k:
            keys.append(k)
    return keys
