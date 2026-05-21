"""Cross-run lessons: record deaths/wins and feed rules into autoplay."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from plugins.sts2.notes import append_hot_note, merge_strategy_rules, read_strategy
from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)

_COMBAT = frozenset({"monster", "elite", "boss"})
_MAX_HISTORY = 80


def run_history_path() -> Path:
    path = sts2_home() / "run_history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def bootstrap_learning_store(*, ascension: int = 1) -> dict[str, Any]:
    """Ensure strategy + history exist so study mode can learn from step one."""
    from plugins.sts2.storage import strategy_dir

    run_history_path()
    strategy_dir()
    data = read_strategy()
    if (data.get("rules") or []):
        return {"bootstrapped": False, "rules": len(data.get("rules") or [])}

    asc = max(0, int(ascension))
    rules = [
        (
            f"进阶{asc}：每回合先看敌人意图；能击杀优先出牌，Buff/Debuff 回合别堆无用格挡。"
        ),
        "敌人回合禁止 end_turn / proceed；非己方出牌阶段用 __wait__。",
        "意图伤害 > 当前格挡时：优先格挡牌/药水，不要空结束回合。",
        "战斗失血后会写入 strategy：下一场同类型战先算格挡线。",
        "阵亡与失误会写入 run_history.jsonl + sts2/reflections.md（【反思·跨局】），并注入【本局记忆】。",
        "Act1 前12层 HP<72% 不进精英；HP<50% 优先营火。",
    ]
    merge_strategy_rules(rules, source="system")
    from plugins.sts2.ironclad_builds import bootstrap_build_rules

    bootstrap_build_rules()
    return {"bootstrapped": True, "rules": len(rules)}


def _hp(player: Any) -> int | None:
    if not isinstance(player, dict):
        return None
    try:
        return int(player.get("hp", player.get("current_hp")))
    except (TypeError, ValueError):
        return None


def _floor(run: Any) -> int:
    if not isinstance(run, dict):
        return 0
    try:
        return int(run.get("floor") or run.get("floor_reached") or 0)
    except (TypeError, ValueError):
        return 0


def _character(run: Any, player: Any) -> str:
    if isinstance(run, dict):
        for key in ("character", "class", "selected_character"):
            if run.get(key):
                return str(run[key])
    if isinstance(player, dict) and player.get("character"):
        return str(player["character"])
    return "unknown"


def detect_outcome_label(
    prev: dict[str, Any] | None,
    nxt: dict[str, Any],
) -> tuple[bool, str]:
    """Return (should_record, label)."""
    nxt_type = str(nxt.get("state_type") or "")
    prev_type = str((prev or {}).get("state_type") or "")

    if nxt_type == "game_over":
        return True, "game_over"

    hp = _hp(nxt.get("player"))
    if hp is not None and hp <= 0:
        return True, "death"

    if prev_type in _COMBAT and nxt_type == "menu":
        return True, "run_end"

    if prev_type in _COMBAT and nxt_type == "rewards":
        return True, "combat_win"

    # Run aborted / back to title without game_over screen
    if prev_type not in ("menu", "") and nxt_type == "menu" and prev_type not in _COMBAT:
        run = nxt.get("run") or (prev or {}).get("run")
        if not run or _floor(run) <= 0:
            return True, "run_end"

    return False, ""


def _last_actions_summary(recent_actions: list) -> str:
    bits: list[str] = []
    for act in recent_actions[-6:]:
        if not isinstance(act, dict):
            continue
        name = act.get("action", "?")
        extra = ""
        if "card_index" in act:
            extra = f" card={act['card_index']}"
        elif "index" in act:
            extra = f" idx={act['index']}"
        bits.append(f"{name}{extra}")
    return " → ".join(bits) if bits else "(no actions)"


def build_lesson_rule(
    label: str,
    prev: dict[str, Any] | None,
    nxt: dict[str, Any],
    recent_actions: list,
) -> str:
    """One-line rule guaranteed to land in strategy.yaml."""
    run = nxt.get("run") or (prev or {}).get("run") or {}
    floor = _floor(run)
    prev_st = str((prev or {}).get("state_type") or "?")
    char = _character(run, nxt.get("player"))
    acts = _last_actions_summary(recent_actions)

    asc = 0
    if isinstance(run, dict) and run.get("ascension") is not None:
        try:
            asc = int(run.get("ascension"))
        except (TypeError, ValueError):
            asc = 0
    asc_tag = f"进阶{asc} " if asc else ""

    if label == "combat_win":
        return (
            f"{char} {asc_tag}Act1 第{floor}层 {prev_st} 胜利："
            f"保持节奏；下一场仍先读意图再出牌。"
        )

    if label == "action_failure":
        low = acts.lower()
        if "bundle_select" in low or "proceed" in low and "bundle" in str(prev_st).lower():
            tail = "卷轴箱 bundle_select：select_bundle(index)→confirm_bundle_selection；勿 proceed。"
        elif "use_potion" in low:
            tail = (
                "药水：确认己方回合、slot 非空、需要目标时带 ENEMY id；"
                "失败则改出牌/格挡，勿连点同一 slot。"
            )
        elif "end_turn" in low or "proceed" in low:
            tail = "敌人回合勿 end_turn/proceed，用 __wait__。"
        elif "play_card" in low:
            tail = "出牌失败：检查 card_index 与 can_play；无牌可出再 end_turn。"
        else:
            tail = f"操作 {acts} 被拒：换合法动作，勿重复同一指令。"
        return f"{char} {asc_tag}第{floor}层 {prev_st} 操作失误（{acts}）：{tail}"

    if label == "stalled_run":
        return (
            f"{char} {asc_tag}第{floor}层 本局卡住（{acts}）："
            f"下局减少无效 proceed；战斗非己方回合用等待。"
        )

    if floor <= 0:
        floor = 1

    if floor <= 3:
        return (
            f"{char} {asc_tag}第{floor}层 {prev_st} 阵亡（{acts}）："
            f"下局前3层优先普通战，首战读意图；攻击回合留费格挡或出牌。"
        )
    if floor <= 8:
        return (
            f"{char} Act1 第{floor}层 {prev_st} 阵亡："
            f"下局血量<40%时优先格挡牌，精英前确保有防。"
        )
    return (
        f"{char} 第{floor}层 {prev_st} 阵亡：复盘末几步「{acts}」，下局同类场面先防。"
    )


def record_outcome(
    label: str,
    prev: dict[str, Any] | None,
    nxt: dict[str, Any],
    *,
    recent_actions: list | None = None,
    llm_summary: str = "",
) -> dict[str, Any]:
    """Persist structured lesson + strategy rule (always writes at least one rule)."""
    recent_actions = recent_actions or []
    run = nxt.get("run") or (prev or {}).get("run") or {}
    floor = _floor(run)
    rule = build_lesson_rule(label, prev, nxt, recent_actions)

    row = {
        "ts": datetime.now(UTC).isoformat(),
        "label": label,
        "floor": floor,
        "character": _character(run, nxt.get("player")),
        "before": str((prev or {}).get("state_type") or ""),
        "after": str(nxt.get("state_type") or ""),
        "rule": rule,
        "actions_tail": _last_actions_summary(recent_actions),
    }
    if llm_summary:
        row["llm_summary"] = llm_summary[:800]

    path = run_history_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Trim file if huge
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_HISTORY:
            path.write_text("\n".join(lines[-_MAX_HISTORY:]) + "\n", encoding="utf-8")
    except OSError:
        pass

    note_body = llm_summary.strip() or rule
    append_hot_note(label, f"{rule}\n\n{note_body}"[:1200])
    merge_strategy_rules([rule], source="lesson")

    logger.info("sts2 lesson recorded: %s floor=%s", label, floor)
    return {"recorded": True, "rule": rule, **row}


def record_action_failure(
    state: dict[str, Any],
    action: dict[str, Any],
    err_msg: str,
) -> dict[str, Any] | None:
    """Log failed clicks; promote to strategy after repeated same error."""
    err = str(err_msg or "").strip()
    if not err:
        return None
    run = state.get("run") or {}
    floor = _floor(run)
    act_name = str(action.get("action") or "?")
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "label": "action_failure",
        "floor": floor,
        "character": _character(run, state.get("player")),
        "before": str(state.get("state_type") or ""),
        "after": str(state.get("state_type") or ""),
        "rule": build_lesson_rule(
            "action_failure",
            state,
            state,
            recent_actions=[action],
        ),
        "error": err[:200],
        "action": act_name,
    }
    path = run_history_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    fp = f"{act_name}|{row['error']}|{row['before']}"
    recent = read_recent_outcomes(20)
    same = sum(
        1
        for r in recent
        if r.get("label") == "action_failure"
        and r.get("error") == row["error"]
        and str(r.get("action") or "") == act_name
    )
    # 仅在第 2 次同类失败时晋升一次，避免每步刷屏「教训已写入」
    promote = same == 2
    if promote:
        merge_strategy_rules(
            [row["rule"]], source="action_failure", force_activate=True
        )
        from plugins.sts2.program_health import report_action_failure

        report_action_failure(err, action, state)
    return {
        "recorded": True,
        "promoted": promote,
        "failure_fingerprint": fp,
        **row,
    }


def read_recent_outcomes(limit: int = 12) -> list[dict[str, Any]]:
    path = run_history_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows[-limit:]


def recent_death_count( *, max_floor: int = 5, limit: int = 5) -> int:
    deaths = 0
    for row in reversed(read_recent_outcomes(limit * 2)):
        if row.get("label") not in ("game_over", "death", "run_end"):
            continue
        if int(row.get("floor") or 99) <= max_floor:
            deaths += 1
        if deaths >= limit:
            break
    return deaths


def should_avoid_elite_early() -> bool:
    """True if last few runs died on low floors — bias map away from elite."""
    n = 0
    for row in reversed(read_recent_outcomes(8)):
        if row.get("label") not in ("game_over", "death", "run_end"):
            continue
        if int(row.get("floor") or 99) <= 5:
            n += 1
        if n >= 2:
            return True
    return False


def lessons_for_screen(state: dict) -> list[str]:
    """Strategy rules relevant to current screen (combat vs macro)."""
    st = str(state.get("state_type") or "")
    if st in _COMBAT:
        return lessons_for_combat(state)
    rules = read_strategy().get("rules") or []
    out: list[str] = []
    for r in rules[-8:]:
        text = str(r).strip()
        if text and text not in out:
            out.append(text)
    if should_avoid_elite_early() and not any(
        "精英" in x or "elite" in x.lower() for x in out
    ):
        out.append("近期低层阵亡多：地图优先 ?/营火/小怪，血线不足勿精英。")
    return out[-6:]


def lessons_for_combat(state: dict) -> list[str]:
    """Rules that should change combat heuristics."""
    rules = read_strategy().get("rules") or []
    out: list[str] = []
    for r in rules:
        text = str(r)
        low = text.lower()
        if any(
            k in low
            for k in (
                "阵亡",
                "格挡",
                "block",
                "防",
                "精英",
                "elite",
                "act1",
                "第1",
                "第2",
                "第3",
                "胜利",
                "节奏",
                "失血",
                "意图",
                "击杀",
                "输出",
                "多怪",
                "boss",
                "进阶",
                "药水",
                "集火",
            )
        ):
            out.append(text)
    if should_avoid_elite_early() and not any("精英" in x or "elite" in x.lower() for x in out):
        out.append("近期低层多次阵亡：Act1 前5层地图优先普通战，少进精英。")
    return out[-8:]


def lessons_summary_for_prompt() -> str:
    """Short block for LLM + logging at autoplay start."""
    outcomes = read_recent_outcomes(5)
    rules = (read_strategy().get("rules") or [])[-6:]
    parts: list[str] = []
    if rules:
        parts.append("跨局规则:\n" + "\n".join(f"- {r}" for r in rules))
    if outcomes:
        parts.append("最近结局:")
        for o in outcomes[-3:]:
            parts.append(
                f"- {o.get('label')} floor={o.get('floor')} "
                f"{o.get('before')}→{o.get('after')}: {o.get('rule', '')[:120]}"
            )
    return "\n".join(parts).strip()


def finalize_trajectory(path: Path | None) -> dict[str, Any]:
    """Scan trajectory for death/game_over if reflect missed it."""
    if path is None or not path.is_file():
        return {"skipped": True}

    prev: dict[str, Any] | None = None
    recent: list[dict[str, Any]] = []
    last_state: dict[str, Any] | None = None

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("type") != "step":
                continue
            st = row.get("state_type")
            act = row.get("action")
            if isinstance(act, dict):
                recent.append(act)
                if len(recent) > 12:
                    recent.pop(0)

            if st:
                last_state = {"state_type": st, "run": row.get("run") or {}}

            if prev and st:
                nxt = {"state_type": st, "run": row.get("run") or {}, "player": row.get("player") or {}}
                ok, label = detect_outcome_label(prev, nxt)
                if ok and label in ("game_over", "death", "run_end"):
                    from plugins.sts2.reflect import reflect_transition

                    return reflect_transition(
                        prev, nxt, recent_actions=recent, use_llm=True
                    )

            if st:
                prev = {"state_type": st, "run": row.get("run") or {}}
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("finalize_trajectory: %s", exc)

    # Many failures without state transition — still nudge strategy
    fail_count = 0
    try:
        text = path.read_text(encoding="utf-8")
        fail_count = text.count('"act_ok": false')
    except OSError:
        pass

    if fail_count >= 3 and last_state:
        return record_outcome(
            "stalled_run",
            prev if prev is not None else last_state,
            last_state,
            recent_actions=recent,
        )

    return {"skipped": True}
