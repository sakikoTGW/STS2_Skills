"""Post-combat / run reflection via auxiliary LLM."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from plugins.sts2.lessons import detect_outcome_label, record_outcome

logger = logging.getLogger(__name__)


def _llm_summarize(prompt: str, *, max_tokens: int = 600) -> str:
    try:
        from plugins.sts2.llm_util import sts2_call_llm

        return sts2_call_llm(
            [
                {
                    "role": "system",
                    "content": (
                        "You summarize Slay the Spire 2 lessons for future runs. "
                        "Be concrete. Output plain text, bullet points ok."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
    except Exception as exc:
        logger.debug("sts2 reflect LLM failed: %s", exc)
        return ""


def reflect_transition(
    prev: Optional[Dict[str, Any]],
    nxt: Dict[str, Any],
    *,
    recent_actions: list,
    use_llm: bool = True,
) -> Dict[str, Any]:
    trigger, label = detect_outcome_label(prev, nxt)
    if not trigger:
        return {"skipped": True}

    from plugins.sts2.lessons import _last_actions_summary, _floor

    prev_type = (prev or {}).get("state_type")
    nxt_type = nxt.get("state_type")
    run = nxt.get("run") or (prev or {}).get("run") or {}
    floor = _floor(run)
    actions_tail = _last_actions_summary(recent_actions)
    snippet = json.dumps(
        {"before": prev_type, "after": nxt_type, "run": run, "player": nxt.get("player")},
        ensure_ascii=False,
    )[:6000]
    actions_txt = json.dumps(recent_actions[-12:], ensure_ascii=False)[:4000]

    want_llm = use_llm and label in ("game_over", "death", "run_end", "combat_win")
    coach_bits = ""
    try:
        from plugins.sts2.manual_learn import read_recent_coach_corrections

        corr = read_recent_coach_corrections(limit=3)
        if corr:
            coach_bits = "\n教练纠正:\n" + "\n".join(f"- {c}" for c in corr)
    except Exception:
        pass

    _rule_style = (
        "写规则必须「当…则…」且绑定本局数据（意图类型、net入伤、能否斩杀、费用）。"
        "禁止无证据的固定血线百分比（例如「HP<50%必防」）。"
        "若本局能击杀却打格挡，写「当回合斩杀线成立时优先输出」。"
        "若因没防致死，写清 net 与 HP 数字。"
    )

    summary = ""
    if want_llm:
        if label in ("game_over", "death", "run_end"):
            summary = _llm_summarize(
                f"铁甲战士 第{floor}层阵亡。\n"
                f"状态: {snippet}\n末几步: {actions_tail}\n操作序列:\n{actions_txt}\n"
                f"{coach_bits}\n\n"
                "用中文写：\n"
                "1) 2-4 条本局具体失误（带数字/牌名）\n"
                "2) 最多 3 条候选规则，每行以「候选：」开头。"
                f"{_rule_style}",
                max_tokens=900,
            )
        else:
            summary = _llm_summarize(
                f"战斗结束: {label}\nState:\n{snippet}\nActions:\n{actions_txt}\n"
                f"{coach_bits}\n\n"
                "写 1-2 条「候选：」规则。"
                f"{_rule_style}",
                max_tokens=450,
            )

    recorded = record_outcome(
        label,
        prev,
        nxt,
        recent_actions=recent_actions,
        llm_summary=summary,
    )

    from plugins.sts2.reflection_journal import (
        append_reflection,
        extract_rules_from_reflection,
    )

    extra: list[str] = []
    if summary and label in ("game_over", "death", "run_end"):
        extra = extract_rules_from_reflection(summary, max_rules=3)
        if extra:
            from plugins.sts2.evolution_loop import propose_rule_changes

            propose_rule_changes(extra, source="reflection")

    append_reflection(
        label=label,
        floor=int(floor or 0),
        rule=str(recorded.get("rule") or ""),
        llm_summary=summary,
        actions_tail=actions_tail,
        extra_rules=extra or None,
    )

    from plugins.sts2.evolution_loop import finalize_run

    fin = finalize_run(
        label=label,
        last_state=nxt,
        llm_summary=summary,
    )

    build_out: dict = {}
    try:
        from plugins.sts2.build_analyzer import analyze_run_end

        build_out = analyze_run_end(prev, nxt, label=label, llm_summary=summary or "")
        if build_out.get("build_review"):
            summary = (summary or "") + "\n\n【构筑复盘】\n" + str(build_out["build_review"])[:1200]
    except Exception:
        pass

    return {
        "reflected": True,
        "label": label,
        "summary": summary[:1500],
        "floor": floor,
        "actions_tail": actions_tail,
        "evolution": fin,
        "build_analysis": build_out,
        **recorded,
    }


def reflect_if_changed(
    prev: Optional[Dict[str, Any]],
    nxt: Dict[str, Any],
    *,
    recent_actions: list,
    use_llm: bool = False,
) -> Dict[str, Any]:
    """Reflect on any detectable outcome (including post-action state)."""
    if not prev or not nxt:
        return {"skipped": True}
    try:
        from plugins.sts2.combat_play_brain import note_combat_aftermath

        note_combat_aftermath(prev, nxt)
    except Exception:
        pass
    return reflect_transition(prev, nxt, recent_actions=recent_actions, use_llm=use_llm)
