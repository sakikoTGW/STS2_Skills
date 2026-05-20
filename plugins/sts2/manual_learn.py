"""Manual-play learning: observe transitions, reflect, propose rules — user approves."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_LAST_STATE: Optional[dict] = None
_ACTIONS: Deque[dict] = deque(maxlen=24)
_CORRECTIONS_PATH = sts2_home() / "coach_corrections.jsonl"


def _manual_learn_enabled() -> bool:
    from plugins.sts2.config import load_sts2_config
    from plugins.sts2.manual_mode import manual_mode_enabled

    cfg = load_sts2_config()
    if manual_mode_enabled():
        return bool(cfg.get("manual_auto_learn", True))
    try:
        from plugins.sts2.agent_learn import agent_learn_enabled

        return agent_learn_enabled()
    except Exception:
        return False


def _use_llm_reflect() -> bool:
    from plugins.sts2.config import load_sts2_config

    return bool(load_sts2_config().get("manual_learn_use_llm", True))


def _state_key(state: Optional[dict]) -> str:
    if not state:
        return ""
    run = state.get("run") or {}
    return "|".join(
        [
            str(state.get("state_type") or ""),
            str(run.get("floor") or ""),
            str(run.get("act") or ""),
            str((state.get("player") or {}).get("hp") or ""),
        ]
    )


def record_action(body: dict) -> None:
    if not body or not _manual_learn_enabled():
        return
    with _LOCK:
        _ACTIONS.append(dict(body))


def record_coach_message(text: str) -> Optional[Dict[str, Any]]:
    """User/TUI correction — episodic memory, optional approve/reject commands."""
    raw = (text or "").strip()
    if not raw:
        return None

    cmd = parse_learn_command(raw)
    if cmd:
        return cmd

    if not _manual_learn_enabled():
        return None

    row = {"ts": datetime.now(timezone.utc).isoformat(), "text": raw[:2000]}
    try:
        _CORRECTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _CORRECTIONS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("coach correction log: %s", exc)

    from plugins.sts2.notes import append_hot_note

    append_hot_note("教练纠正", raw[:1500])
    try:
        from plugins.sts2.combat_turn_plan import record_coach_hint

        if any(
            k in raw
            for k in (
                "转向",
                "包围",
                "boss",
                "Boss",
                "蟹",
                "势不可挡",
                "循环",
                "下回合",
                "易伤",
                "格挡",
            )
        ):
            record_coach_hint(raw)
    except Exception:
        pass
    return {"recorded": True, "kind": "coach_correction"}


def read_recent_coach_corrections(*, limit: int = 5) -> List[str]:
    if not _CORRECTIONS_PATH.is_file():
        return []
    lines: List[str] = []
    try:
        for line in _CORRECTIONS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                t = str(row.get("text") or "").strip()
                if t:
                    lines.append(t)
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return lines[-limit:]


def parse_learn_command(text: str) -> Optional[Dict[str, Any]]:
    """Chat: 采纳规则1 / 采纳全部 / 拒绝规则2"""
    s = (text or "").strip()
    if not s:
        return None

    if re.search(r"采纳\s*全部|全部采纳|approve\s*all", s, re.I):
        from plugins.sts2.evolution_loop import approve_pending_rules

        return {"learn_command": True, **approve_pending_rules(all=True)}

    m = re.search(r"(?:采纳|通过|approve)\s*规则?\s*(\d+)", s, re.I)
    if m:
        from plugins.sts2.evolution_loop import approve_pending_rules

        return {
            "learn_command": True,
            **approve_pending_rules(indices=[int(m.group(1)) - 1]),
        }

    m = re.search(r"(?:拒绝|否决|reject)\s*规则?\s*(\d+)", s, re.I)
    if m:
        from plugins.sts2.evolution_loop import reject_pending_rules

        return {
            "learn_command": True,
            **reject_pending_rules(indices=[int(m.group(1)) - 1]),
        }

    if re.search(r"拒绝\s*全部|全部拒绝", s, re.I):
        from plugins.sts2.evolution_loop import reject_pending_rules

        return {"learn_command": True, **reject_pending_rules(all=True)}
    return None


def tick(
    nxt: dict,
    *,
    action: Optional[dict] = None,
) -> Dict[str, Any]:
    """Call after get_state / sts2_act with fresh game state."""
    global _LAST_STATE
    if not _manual_learn_enabled() or not isinstance(nxt, dict):
        return {"skipped": True}

    if action:
        record_action(action)

    from plugins.sts2.evolution_loop import accumulate_step_reward, begin_run

    if not _LAST_STATE:
        begin_run()

    prev = _LAST_STATE
    out: Dict[str, Any] = {"skipped": False}
    key_prev, key_nxt = _state_key(prev), _state_key(nxt)
    if prev and key_prev != key_nxt:
        accumulate_step_reward(0.05 if action else 0.0, nxt, act_ok=True)
        try:
            from plugins.sts2.reflect import reflect_if_changed

            ref = reflect_if_changed(
                prev,
                nxt,
                recent_actions=list(_ACTIONS),
                use_llm=_use_llm_reflect(),
            )
            out["reflect"] = ref
            if ref.get("reflected"):
                _notify_reflection(ref)
        except Exception as exc:
            logger.debug("manual_learn reflect: %s", exc)
            out["reflect_error"] = str(exc)
        try:
            from plugins.sts2.map_route_learn import observe_transition as map_observe

            out["map_route"] = map_observe(prev, nxt, action=action)
        except Exception as exc:
            logger.debug("map_route observe: %s", exc)
        try:
            from plugins.sts2.combat_turn_plan import observe_transition as combat_observe

            combat_observe(prev, nxt)
        except Exception:
            pass

    with _LOCK:
        _LAST_STATE = dict(nxt)
    return out


def reset_session() -> None:
    global _LAST_STATE
    with _LOCK:
        _LAST_STATE = None
        _ACTIONS.clear()


def _notify_reflection(ref: Dict[str, Any]) -> None:
    from plugins.sts2.evolution_loop import read_pending

    pending = read_pending()
    if not pending:
        return
    try:
        from plugins.sts2.coach_channel import append_outbox

        lines = [
            f"**【学习·待你确认】** {ref.get('label', '?')} 第{ref.get('floor', '?')}层",
            "",
        ]
        if ref.get("summary"):
            lines.append(str(ref["summary"])[:600])
            lines.append("")
        lines.append("归纳了候选规则（**未自动生效**），请回复：")
        for i, p in enumerate(pending[:6], 1):
            lines.append(f"{i}. {p.get('text', '')[:200]}")
        lines.append("")
        lines.append("→ 聊天 **「采纳规则1」** 或工具 `sts2_learn action=approve index=1`")
        append_outbox("\n".join(lines))
        from plugins.sts2.tui_emit import emit_sts2_to_tui

        emit_sts2_to_tui(
            f"【学习】{len(pending)} 条待确认规则 — 采纳规则1 / 采纳全部 / 拒绝规则2"
        )
    except Exception as exc:
        logger.debug("notify reflection: %s", exc)


def build_learn_context(*, max_chars: int = 2200) -> str:
    """Injected into play_brief — not static playbooks."""
    if not _manual_learn_enabled():
        return ""

    parts: List[str] = []

    corrections = read_recent_coach_corrections(limit=4)
    if corrections:
        parts.append(
            "【教练纠正·优先】\n"
            + "\n".join(f"- {c[:280]}" for c in corrections)
        )

    try:
        from plugins.sts2.reflection_journal import read_last_reflection_summary

        last = read_last_reflection_summary(max_chars=500)
        if last and "尚无" not in last:
            parts.append(f"【上局复盘摘录】\n{last}")
    except Exception:
        pass

    try:
        from plugins.sts2.evolution_loop import read_pending

        pending = read_pending()
        if pending:
            bits = ["【待采纳规则·你说「采纳规则N」才写入策略】"]
            for i, p in enumerate(pending[:6], 1):
                bits.append(f"{i}. {str(p.get('text') or '')[:200]}")
            parts.append("\n".join(bits))
    except Exception:
        pass

    try:
        from plugins.sts2.evolution_loop import ranked_rules_for_prompt

        ranked = ranked_rules_for_prompt(limit=4)
        if ranked:
            parts.append(
                "【已生效倾向·来自过往对局，可能错，用本回合数据覆盖】\n"
                + "\n".join(f"- {t[:180]}" for t in ranked)
            )
    except Exception:
        pass

    try:
        from plugins.sts2.map_route_learn import route_rules_for_prompt

        rrules = route_rules_for_prompt()
        if rrules:
            parts.append(
                "【已采纳·地图路线】\n" + "\n".join(f"- {t[:180]}" for t in rrules)
            )
    except Exception:
        pass

    try:
        from plugins.sts2.build_analyzer import format_build_journal_tail

        bj = format_build_journal_tail()
        if bj:
            parts.append(bj)
    except Exception:
        pass

    text = "\n\n".join(parts).strip()
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def ensure_manual_bootstrap() -> None:
    """Seed learning store without static HP% heuristics."""
    from plugins.sts2.manual_mode import manual_mode_enabled
    from plugins.sts2.notes import read_strategy

    if not manual_mode_enabled():
        return
    if (read_strategy().get("rules") or []):
        return
    from plugins.sts2.config import load_sts2_config

    if not load_sts2_config().get("manual_skip_static_bootstrap", True):
        from plugins.sts2.lessons import bootstrap_learning_store

        bootstrap_learning_store()
        return

    from plugins.sts2.notes import merge_strategy_rules

    merge_strategy_rules(
        [
            "规则必须「当…则…」且来自本局意图/伤害/斩杀线数据；禁止无上下文的固定血线百分比。",
            "教练当场纠正优先于自动归纳；待采纳规则须用户「采纳规则N」后才生效。",
            "战斗：先算 net 入伤与斩杀线；能击杀时优先输出，非攻击意图回合少堆无用格挡。",
            "地图：每幕先通读整图节点再选路；精英/事件/营火权衡用本账号 route 统计与采纳规则，勿套泛攻略。",
        ],
        source="manual_bootstrap",
        force_activate=True,
    )
