"""Local STS2 knowledge base (auto-filled from game wiki API)."""



from __future__ import annotations



import logging

import re

from datetime import datetime, timezone

from pathlib import Path

from typing import Any, Dict, List, Optional, Tuple



import yaml



from plugins.sts2.storage import sts2_home



logger = logging.getLogger(__name__)



_KINDS = ("cards", "relics", "enemies")





def knowledge_dir() -> Path:

    path = sts2_home() / "knowledge"

    path.mkdir(parents=True, exist_ok=True)

    return path





def knowledge_path(kind: str) -> Path:

    if kind not in _KINDS:

        kind = "cards"

    return knowledge_dir() / f"{kind}.yaml"





def _empty_store() -> Dict[str, Any]:

    return {"version": 0, "entries": {}}





def load_store(kind: str) -> Dict[str, Any]:

    path = knowledge_path(kind)

    if not path.is_file():

        return _empty_store()

    try:

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    except Exception:

        return _empty_store()

    if not isinstance(data, dict):

        return _empty_store()

    data.setdefault("entries", {})

    if not isinstance(data["entries"], dict):

        data["entries"] = {}

    return data





def save_store(kind: str, data: Dict[str, Any]) -> None:

    data = dict(data)

    data["version"] = int(data.get("version", 0)) + 1

    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    knowledge_path(kind).write_text(

        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),

        encoding="utf-8",

    )





def get_entry(kind: str, item_id: str) -> Optional[Dict[str, Any]]:

    key = _norm_id(item_id)

    if not key:

        return None

    return (load_store(kind).get("entries") or {}).get(key)





def has_entry(kind: str, item_id: str) -> bool:

    return get_entry(kind, item_id) is not None





def _norm_id(item_id: str) -> str:

    return str(item_id or "").strip().upper()





def upsert_entry(kind: str, item_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:

    key = _norm_id(item_id)

    if not key:

        return {}

    data = load_store(kind)

    entries = data.setdefault("entries", {})

    merged = dict(entries.get(key) or {})

    merged.update(entry)

    merged["id"] = key

    merged.setdefault("curated_at", datetime.now(timezone.utc).isoformat())

    entries[key] = merged

    save_store(kind, data)

    return merged





def list_rules_from_knowledge(*, limit: int = 12) -> List[str]:

    out: List[str] = []

    for kind in _KINDS:

        for ent in (load_store(kind).get("entries") or {}).values():

            rule = str(ent.get("rule") or "").strip()

            if rule and rule not in out:

                out.append(rule)

    return out[-limit:]





def card_reward_bonus(card_id: str) -> float:

    ent = get_entry("cards", card_id)

    if not ent:

        return 0.0

    try:

        return float(ent.get("reward_bonus", 0))

    except (TypeError, ValueError):

        return 0.0





def combat_card_bonus(card_id: str) -> float:

    ent = get_entry("cards", card_id)

    if not ent:

        return 0.0

    try:

        return float(ent.get("combat_bonus", 0))

    except (TypeError, ValueError):

        return 0.0





def _wiki_results(payload: Any) -> List[Dict[str, Any]]:

    if isinstance(payload, list):

        return [x for x in payload if isinstance(x, dict)]

    if not isinstance(payload, dict):

        return []

    for key in ("results", "items", "entries", "data"):

        raw = payload.get(key)

        if isinstance(raw, list):

            return [x for x in raw if isinstance(x, dict)]

    return []





def _pick_best_wiki_match(results: List[Dict[str, Any]], *, query: str, item_id: str) -> Optional[Dict[str, Any]]:

    if not results:

        return None

    q = _norm_id(item_id) or query.strip().upper()

    for row in results:

        rid = _norm_id(str(row.get("id") or row.get("card_id") or row.get("relic_id") or ""))

        if rid and rid == q:

            return row

    return results[0]





def _text_blob(entry: Dict[str, Any]) -> str:

    parts: List[str] = []

    for key in ("description", "text", "effect", "flavor", "summary"):

        v = entry.get(key)

        if v:

            parts.append(str(v))

    return " ".join(parts).lower()





def analyze_wiki_entry(entry: Dict[str, Any], *, kind: str = "cards") -> Dict[str, Any]:

    """Heuristic tags + scores from wiki text (no LLM)."""

    cid = _norm_id(str(entry.get("id") or entry.get("card_id") or entry.get("relic_id") or ""))

    name = str(entry.get("name") or entry.get("title") or cid)

    text = _text_blob(entry)

    tags: List[str] = []



    if kind == "relics":

        reward_bonus = 12.0

        combat_bonus = 8.0

        if "energy" in text or "能量" in text:

            reward_bonus += 15.0

            tags.append("energy")

        if "strength" in text or "力量" in text:

            combat_bonus += 12.0

            tags.append("strength")

        rule = f"遗物 {name}：{tags[0] if tags else '泛用'}加成，奖励屏优先拿。"

        return {

            "id": cid,

            "name": name,

            "tags": tags,

            "reward_bonus": reward_bonus,

            "combat_bonus": combat_bonus,

            "rule": rule[:160],

            "source": "wiki_heuristic",

        }



    if re.search(r"\battack\b|攻击", text) or "damage" in text or "伤害" in text:

        tags.append("attack")

    if "block" in text or "格挡" in text:

        tags.append("block")

    if "power" in text or "能力" in text or "strength" in text or "力量" in text:

        tags.append("power")

    if "exhaust" in text or "消耗" in text:

        tags.append("exhaust")

    if "vulnerable" in text or "易伤" in text or "weak" in text or "虚弱" in text:

        tags.append("debuff")

    if "aoe" in text or "all enemy" in text or "所有敌人" in text:

        tags.append("aoe")



    reward_bonus = 10.0

    combat_bonus = 8.0

    if "power" in tags or "strength" in text:

        reward_bonus += 22.0

        combat_bonus += 14.0

    if "attack" in tags:

        combat_bonus += 10.0

    if "block" in tags:

        combat_bonus += 6.0

        reward_bonus += 4.0

    if "curse" in text or "诅咒" in text:

        reward_bonus -= 80.0

        combat_bonus -= 80.0

    if "status" in text and "wound" in text:

        reward_bonus -= 25.0



    tag_hint = "/".join(tags[:3]) if tags else "unknown"

    rule = f"卡牌 {name}（{tag_hint}）：Wiki 标记；选牌+{int(reward_bonus)} 战斗+{int(combat_bonus)}。"

    return {

        "id": cid,

        "name": name,

        "tags": tags,

        "reward_bonus": reward_bonus,

        "combat_bonus": combat_bonus,

        "rule": rule[:160],

        "source": "wiki_heuristic",

    }





def _llm_distill_rule(name: str, wiki_text: str, *, tags: List[str]) -> str:

    try:

        from plugins.sts2.llm_util import sts2_call_llm



        raw = sts2_call_llm(

            [

                {

                    "role": "system",

                    "content": (

                        "You distill Slay the Spire 2 wiki into ONE actionable rule "

                        "for future autoplay (Chinese, <= 80 chars). No fluff."

                    ),

                },

                {

                    "role": "user",

                    "content": (

                        f"Item: {name}\nTags: {', '.join(tags)}\nWiki:\n{wiki_text[:2500]}\n"

                        "Output one line only."

                    ),

                },

            ],

            max_tokens=120,

            temperature=0.2,

        )

        return raw.split("\n")[0][:160] if raw else ""

    except Exception as exc:

        logger.debug("knowledge LLM distill failed: %s", exc)

        return ""





def fetch_and_store(

    kind: str,

    item_id: str,

    *,

    query: str = "",

    use_llm: bool = False,

) -> Tuple[Optional[Dict[str, Any]], str]:

    """Wiki lookup → local yaml. Returns (entry, rule_to_merge)."""

    key = _norm_id(item_id)

    if not key:

        return None, ""

    if has_entry(kind, key):

        ent = get_entry(kind, key) or {}

        return ent, str(ent.get("rule") or "")

    if kind == "enemies":
        try:
            from plugins.sts2.huiji_kb.store import lookup_enemy, to_knowledge_entry

            huiji = lookup_enemy(key)
            if huiji:
                analyzed = to_knowledge_entry(huiji)
                upsert_entry(kind, key, analyzed)
                return analyzed, str(analyzed.get("rule") or "")
        except Exception as exc:
            logger.debug("huiji_kb lookup failed for %s: %s", key, exc)

    from plugins.sts2 import client as sts2_client



    q = (query or key).strip()

    try:

        item_type_lookup = {"cards": "card", "relics": "relic", "enemies": "enemy"}

        item_type = item_type_lookup.get(kind, "all")

        status, payload = sts2_client.wiki_search(

            q,

            item_type=item_type,

            limit=5,

        )

    except Exception as exc:

        logger.debug("wiki_search failed for %s: %s", q, exc)

        return None, ""



    if status != 200:

        # Fallback: search all types

        try:

            status, payload = sts2_client.wiki_search(q, item_type="all", limit=5)

        except Exception:

            return None, ""

    if status != 200:

        return None, ""



    match = _pick_best_wiki_match(_wiki_results(payload), query=q, item_id=key)

    if not match:

        return None, ""



    analyzed = analyze_wiki_entry(match, kind=kind)

    if not analyzed.get("id"):

        analyzed["id"] = key

    wiki_text = _text_blob(match)

    rule = str(analyzed.get("rule") or "")

    if use_llm and wiki_text:

        distilled = _llm_distill_rule(str(analyzed.get("name") or q), wiki_text, tags=analyzed.get("tags") or [])

        if distilled:

            analyzed["rule"] = distilled

            rule = distilled

    analyzed["wiki_snippet"] = wiki_text[:400]



    upsert_entry(kind, key, analyzed)

    return analyzed, rule