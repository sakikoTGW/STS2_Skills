"""Load cross-run memory every step — rules must affect play, not sit in a file."""

from __future__ import annotations

_CACHE: list[str] = []
_CACHE_TS = 0.0


def refresh_memory_cache() -> list[str]:
    """Rules + recent death lessons (re-read each call in study mode)."""
    global _CACHE, _CACHE_TS
    import time

    from plugins.sts2.knowledge import list_rules_from_knowledge
    from plugins.sts2.lessons import lessons_for_combat, read_recent_outcomes
    from plugins.sts2.notes import read_strategy

    now = time.time()
    if _CACHE and now - _CACHE_TS < 2.0:
        return _CACHE

    lines: list[str] = []
    for r in list_rules_from_knowledge(limit=8):
        if r not in lines:
            lines.append(r)
    try:
        from plugins.sts2.evolution_loop import ranked_rules_for_prompt

        for r in ranked_rules_for_prompt(limit=10):
            if r not in lines:
                lines.append(r)
    except Exception:
        pass
    for r in (read_strategy().get("rules") or [])[-10:]:
        t = str(r).strip()
        if t and t not in lines:
            lines.append(t)

    for row in read_recent_outcomes(4):
        rule = str(row.get("rule") or "").strip()
        if rule and rule not in lines:
            lines.append(rule)

    lines.extend(lessons_for_combat({}))
    # dedupe preserve order
    seen = set()
    out: list[str] = []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            out.append(ln)
    _CACHE = out[-12:]
    _CACHE_TS = now
    return _CACHE


def memory_prefix_for_commentary() -> str:
    mem = refresh_memory_cache()
    if not mem:
        return ""
    return "【本局记忆】\n" + "\n".join(f"· {m[:120]}" for m in mem[-6:]) + "\n"
