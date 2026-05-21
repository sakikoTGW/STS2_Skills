"""Post-run build analysis — personal archetype journal + optional LLM review."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from plugins.sts2.build_knowledge import (
    _append_journal,
    _character,
    _floor_act,
    _load_profile,
    _save_profile,
    detect_archetype_from_catalog,
    journal_path,
    list_archetypes,
    web_digest,
)

logger = logging.getLogger(__name__)


def _deck_ids(state: dict) -> list[str]:
    ids: list[str] = []
    player = state.get("player") or {}
    for key in ("deck", "master_deck", "cards", "draw_pile", "discard_pile"):
        for c in player.get(key) or []:
            if isinstance(c, dict):
                cid = str(c.get("id") or "").upper()
                if cid:
                    ids.append(cid)
    return ids


def analyze_run_end(
    prev: dict | None,
    nxt: dict,
    *,
    label: str = "",
    llm_summary: str = "",
) -> dict[str, Any]:
    """Called on game_over / run_end — update profile + optional LLM build review."""
    from plugins.sts2.config import load_sts2_config

    if not load_sts2_config().get("build_analyze_after_run", True):
        return {"skipped": True}

    state = nxt if isinstance(nxt, dict) else prev
    if not state:
        return {"skipped": True}

    char = _character(state)
    arch_id, _ = detect_archetype_from_catalog(state)
    floor, act = _floor_act(state)
    win = label not in ("death", "game_over") and str(nxt.get("state_type") or "") not in (
        "game_over",
    )
    if label in ("death", "game_over"):
        win = False

    deck = _deck_ids(state)
    counts = Counter(deck)

    row = {
        "ts": datetime.now(UTC).isoformat(),
        "event": "run_end",
        "label": label,
        "char": char,
        "archetype": arch_id,
        "act": act,
        "floor": floor,
        "win": win,
        "deck_size": len(deck),
        "top_cards": counts.most_common(12),
    }
    _append_journal(row)
    _update_profile(char, arch_id, floor, win, deck)

    out: dict[str, Any] = {"recorded": True, "archetype": arch_id, "floor": floor, "win": win}

    if not load_sts2_config().get("build_analyze_use_llm", True):
        out["llm_skipped"] = True
        return out

    try:
        summary = _llm_build_review(state, label=label, deck=deck, llm_prior=llm_summary)
        out["build_review"] = summary
        if summary:
            _append_journal(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "event": "build_review",
                    "text": summary[:3000],
                }
            )
    except Exception as exc:
        logger.debug("build_analyzer llm: %s", exc)
        out["llm_error"] = str(exc)

    return out


def _update_profile(char: str, arch_id: str, floor: int, win: bool, deck: list[str]) -> None:
    prof = _load_profile()
    ch = prof.setdefault("characters", {}).setdefault(char.upper(), {"runs": []})
    runs: list[dict] = list(ch.get("runs") or [])
    runs.append(
        {
            "ts": datetime.now(UTC).isoformat(),
            "archetype": arch_id,
            "floor": floor,
            "win": win,
            "deck_core": list(dict.fromkeys(deck))[:20],
        }
    )
    ch["runs"] = runs[-30:]
    arch_counts = Counter(r.get("archetype") for r in ch["runs"])
    ch["favorite_archetype"] = arch_counts.most_common(1)[0][0] if arch_counts else arch_id
    _save_profile(prof)


def _llm_build_review(
    state: dict,
    *,
    label: str,
    deck: list[str],
    llm_prior: str = "",
) -> str:
    from plugins.sts2.llm_util import sts2_call_llm
    from plugins.sts2.run_objective import llm_run_objective_system

    char = _character(state)
    arch_id, _ = detect_archetype_from_catalog(state)
    arch_names = [a.get("name") for a in list_archetypes(char)]
    floor, act = _floor_act(state)
    web = web_digest(800)

    raw = sts2_call_llm(
        [
            {
                "role": "system",
                "content": (
                    "你是 STS2 构筑分析师。第一目的通关整局，第二目的控战损。"
                    "根据本局牌组与结局，分析构筑是否成型、是否该转型、下局改进。"
                    + llm_run_objective_system()
                    + "输出：①本局主轴评价 ②核心缺件/废牌 ③下局抓牌方向 "
                    "④1-2条「候选：」条件化规则（绑定 Act/层/牌名，禁止固定血线%）。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"角色={char} Act{act} 第{floor}层 结局={label}\n"
                    f"检测主轴={arch_id} 可选流派={arch_names}\n"
                    f"牌组ID({len(deck)}): {', '.join(deck[:35])}\n"
                    f"Prior reflection:\n{llm_prior[:600]}\n"
                    f"Web digest:\n{web}\n"
                ),
            },
        ],
        max_tokens=520,
        temperature=0.28,
    )
    if raw:
        from plugins.sts2.evolution_loop import propose_rule_changes
        from plugins.sts2.map_route_learn import _extract_candidate_rules

        rules = _extract_candidate_rules(raw)
        if rules:
            propose_rule_changes(rules, source="build_analyzer")
    return raw


def format_build_journal_tail(*, limit: int = 3) -> str:
    path = journal_path()
    if not path.is_file():
        return ""
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit * 3 :]:
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return ""
    reviews = [r for r in rows if r.get("event") == "build_review"]
    if not reviews:
        return ""
    return "【最近构筑复盘】\n" + str(reviews[-1].get("text", ""))[:800]
