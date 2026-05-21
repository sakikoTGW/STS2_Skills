"""hot_notes + strategy.yaml for cross-turn learning."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml

from plugins.sts2.storage import hot_notes_path, strategy_path


def read_hot_notes() -> str:
    path = hot_notes_path()
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def append_hot_note(section: str, body: str, *, max_chars: int = 12000) -> None:
    path = hot_notes_path()
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    block = f"\n\n## {section} ({stamp})\n{body.strip()}\n"
    existing = path.read_text(encoding="utf-8") if path.is_file() else "# STS2 hot notes\n"
    merged = (existing + block).strip() + "\n"
    if len(merged) > max_chars:
        merged = merged[-max_chars:]
        merged = merged[merged.find("\n## ") :].lstrip() if "\n## " in merged else merged
        merged = "# STS2 hot notes (trimmed)\n" + merged
    path.write_text(merged, encoding="utf-8")


def read_strategy() -> dict[str, Any]:
    path = strategy_path()
    if not path.is_file():
        return {"version": 0, "rules": []}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"version": 0, "rules": []}
    if not isinstance(data, dict):
        return {"version": 0, "rules": []}
    data.setdefault("rules", [])
    return data


def merge_strategy_rules(
    new_rules: list[str],
    *,
    source: str = "merge",
    force_activate: bool = False,
) -> dict[str, Any]:
    """Route through evolution loop (measure → gate → keep/rollback)."""
    from plugins.sts2.evolution_loop import propose_rule_changes

    cleaned = [str(r).strip() for r in new_rules if str(r).strip()]
    if not cleaned:
        return read_strategy()
    propose_rule_changes(
        cleaned,
        source=source,
        force_activate=force_activate
        or source in ("system", "bootstrap", "supervisor", "action_failure", "lesson"),
    )
    return read_strategy()


def recall_block() -> str:
    from plugins.sts2.lessons import lessons_summary_for_prompt

    notes = read_hot_notes()
    strat = read_strategy()
    rules = strat.get("rules") or []
    parts = []
    cross = lessons_summary_for_prompt()
    if cross:
        parts.append(cross)
    try:
        from plugins.sts2.evolution_loop import ranked_rules_for_prompt

        ranked = ranked_rules_for_prompt(limit=12)
        if ranked:
            parts.append("Strategy rules (进化排序):\n" + "\n".join(f"- {r}" for r in ranked))
        elif rules:
            parts.append("Strategy rules:\n" + "\n".join(f"- {r}" for r in rules[-12:]))
    except Exception:
        if rules:
            parts.append("Strategy rules:\n" + "\n".join(f"- {r}" for r in rules[-12:]))
    if notes:
        parts.append("Hot notes:\n" + notes[-4000:])
    return "\n\n".join(parts).strip()
