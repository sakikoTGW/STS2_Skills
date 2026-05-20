"""Closed-loop strategy evolution: measure → propose → gate → keep/rollback."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from plugins.sts2.storage import strategy_path, sts2_home

logger = logging.getLogger(__name__)

_RESULTS = "results.jsonl"
_REGISTRY = "rule_registry.yaml"
_PENDING = "pending_rules.json"
_BASELINE = "evolution_baseline.json"

_RUN: Dict[str, Any] = {
    "id": "",
    "reward_sum": 0.0,
    "steps": 0,
    "fail_steps": 0,
    "max_floor": 0,
    "max_act": 1,
    "started_at": "",
}


def evolution_dir() -> Path:
    p = sts2_home() / "evolution"
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_path() -> Path:
    return evolution_dir() / _RESULTS


def registry_path() -> Path:
    return evolution_dir() / _REGISTRY


def pending_path() -> Path:
    return evolution_dir() / _PENDING


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rule_id(text: str) -> str:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    return f"r_{h}"


def _floor(run: Any) -> int:
    if not isinstance(run, dict):
        return 0
    try:
        return int(run.get("floor") or run.get("floor_reached") or 0)
    except (TypeError, ValueError):
        return 0


def _act(run: Any) -> int:
    if not isinstance(run, dict):
        return 1
    try:
        return max(1, int(run.get("act") or 1))
    except (TypeError, ValueError):
        return 1


def read_registry() -> Dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return {"version": 0, "rules": [], "updated_at": ""}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"version": 0, "rules": [], "updated_at": ""}
    if not isinstance(data, dict):
        return {"version": 0, "rules": [], "updated_at": ""}
    data.setdefault("rules", [])
    return data


def write_registry(data: Dict[str, Any]) -> None:
    data["updated_at"] = _now_iso()
    data["version"] = int(data.get("version", 0)) + 1
    registry_path().write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _sync_strategy_yaml_from_registry(data)


def _sync_strategy_yaml_from_registry(data: Dict[str, Any]) -> None:
    """Keep strategy.yaml aligned with active registry rules (backward compat)."""
    active = [
        str(r.get("text") or "").strip()
        for r in data.get("rules") or []
        if str(r.get("status") or "active") == "active" and str(r.get("text") or "").strip()
    ]
    active.sort(key=lambda t: _score_for_text(t, data), reverse=True)
    payload = {
        "version": data.get("version", 0),
        "updated_at": data.get("updated_at", ""),
        "evolution": True,
        "rules": active[:40],
    }
    strategy_path().write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _score_for_text(text: str, data: Dict[str, Any]) -> float:
    for r in data.get("rules") or []:
        if str(r.get("text") or "").strip() == text.strip():
            return float(r.get("score") or 0)
    return 0.0


def read_results(limit: int = 50) -> List[Dict[str, Any]]:
    path = results_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
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


def append_result(row: Dict[str, Any]) -> None:
    path = results_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 200:
            path.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_pending() -> List[Dict[str, Any]]:
    path = pending_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data) if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def write_pending(items: List[Dict[str, Any]]) -> None:
    pending_path().write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def begin_run() -> str:
    """Start per-run reward / floor tracking."""
    rid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    global _RUN
    _RUN = {
        "id": rid,
        "reward_sum": 0.0,
        "steps": 0,
        "fail_steps": 0,
        "max_floor": 0,
        "max_act": 1,
        "started_at": _now_iso(),
    }
    _snapshot_strategy_for_rollback()
    return rid


def _snapshot_strategy_for_rollback() -> None:
    src = strategy_path()
    if not src.is_file():
        return
    bak = evolution_dir() / "strategy_rollback.yaml"
    try:
        shutil.copy2(src, bak)
    except OSError:
        pass


def _rollback_strategy() -> bool:
    bak = evolution_dir() / "strategy_rollback.yaml"
    if not bak.is_file():
        return False
    try:
        shutil.copy2(bak, strategy_path())
        reg = read_registry()
        _sync_strategy_yaml_from_registry(reg)
        return True
    except OSError:
        return False


def accumulate_step_reward(
    reward: float,
    state: Optional[Dict[str, Any]] = None,
    *,
    act_ok: bool = True,
) -> None:
    global _RUN
    if not _RUN.get("id"):
        begin_run()
    _RUN["reward_sum"] = float(_RUN.get("reward_sum", 0)) + float(reward or 0)
    _RUN["steps"] = int(_RUN.get("steps", 0)) + 1
    if not act_ok:
        _RUN["fail_steps"] = int(_RUN.get("fail_steps", 0)) + 1
    if isinstance(state, dict):
        run = state.get("run") or {}
        _RUN["max_floor"] = max(int(_RUN.get("max_floor", 0)), _floor(run))
        _RUN["max_act"] = max(int(_RUN.get("max_act", 1)), _act(run))


def _rolling_baseline(*, window: int = 8) -> Dict[str, float]:
    rows = read_results(window)
    if not rows:
        return {"median_max_floor": 0.0, "median_max_act": 1.0, "n": 0}
    floors = sorted(float(r.get("max_floor") or 0) for r in rows)
    acts = sorted(float(r.get("max_act") or 1) for r in rows)
    mid = len(floors) // 2
    return {
        "median_max_floor": floors[mid] if floors else 0.0,
        "median_max_act": acts[mid] if acts else 1.0,
        "n": float(len(rows)),
    }


def _save_baseline(b: Dict[str, float]) -> None:
    p = evolution_dir() / _BASELINE
    try:
        p.write_text(json.dumps(b, indent=2), encoding="utf-8")
    except OSError:
        pass


def propose_rule_changes(
    rules: List[str],
    *,
    source: str = "reflection",
    force_activate: bool = False,
) -> Dict[str, Any]:
    """Queue rule changes; system/bootstrap rules can force_activate."""
    cleaned = [str(r).strip() for r in rules if str(r).strip()]
    if not cleaned:
        return {"proposed": 0}

    if force_activate or source in ("system", "bootstrap", "supervisor", "knowledge"):
        return _activate_rules(cleaned, source=source)

    pending = read_pending()
    added = 0
    for text in cleaned:
        rid = _rule_id(text)
        if any(p.get("id") == rid for p in pending):
            continue
        pending.append(
            {
                "id": rid,
                "text": text[:240],
                "source": source,
                "proposed_at": _now_iso(),
                "run_id": _RUN.get("id", ""),
            }
        )
        added += 1
    write_pending(pending)
    return {"proposed": added, "pending_total": len(pending)}


def _activate_rules(rules: List[str], *, source: str) -> Dict[str, Any]:
    data = read_registry()
    reg_rules: List[Dict[str, Any]] = list(data.get("rules") or [])
    by_id = {str(r.get("id")): r for r in reg_rules}
    activated = 0
    for text in rules:
        text = text.strip()[:240]
        if not text:
            continue
        rid = _rule_id(text)
        if rid in by_id:
            row = by_id[rid]
            row["status"] = "active"
            row["score"] = float(row.get("score") or 0) + 0.5
        else:
            reg_rules.append(
                {
                    "id": rid,
                    "text": text,
                    "score": 1.0 if source == "system" else 0.3,
                    "status": "active",
                    "source": source,
                    "added_at": _now_iso(),
                    "runs_seen": 0,
                    "runs_helped": 0,
                }
            )
            activated += 1
    # cap registry
    reg_rules = sorted(
        reg_rules,
        key=lambda r: float(r.get("score") or 0),
        reverse=True,
    )[:60]
    data["rules"] = reg_rules
    write_registry(data)
    return {"activated": activated, "total": len(reg_rules)}


def _retire_pending(*, demote_score: float = 0.4) -> None:
    pending = read_pending()
    if not pending:
        return
    data = read_registry()
    reg = {str(r.get("id")): r for r in data.get("rules") or []}
    for p in pending:
        rid = str(p.get("id") or "")
        if rid in reg:
            reg[rid]["status"] = "retired"
            reg[rid]["score"] = max(0.0, float(reg[rid].get("score") or 0) - demote_score)
    data["rules"] = list(reg.values())
    write_registry(data)
    write_pending([])


def _promote_pending() -> int:
    pending = read_pending()
    if not pending:
        return 0
    texts = [str(p.get("text") or "") for p in pending if p.get("text")]
    out = _activate_rules(texts, source="evolution_gate")
    write_pending([])
    return int(out.get("activated") or 0)


def approve_pending_rules(
    *,
    indices: Optional[List[int]] = None,
    all: bool = False,
) -> Dict[str, Any]:
    """User confirms proposed rules (manual learn / coach chat)."""
    pending = read_pending()
    if not pending:
        return {"approved": 0, "message": "没有待采纳规则"}
    if all:
        chosen = list(pending)
    elif indices is not None:
        chosen = []
        for i in indices:
            if 0 <= int(i) < len(pending):
                chosen.append(pending[int(i)])
    else:
        return {"approved": 0, "message": "需要 index 或 all=true"}
    texts = [str(p.get("text") or "") for p in chosen if p.get("text")]
    if not texts:
        return {"approved": 0, "message": "无效序号"}
    out = _activate_rules(texts, source="user_approved")
    remain = [p for p in pending if p not in chosen]
    write_pending(remain)
    try:
        from plugins.sts2.coach_channel import append_outbox

        append_outbox(
            f"**【学习·已采纳】** {len(texts)} 条\n"
            + "\n".join(f"- {t[:200]}" for t in texts)
        )
    except Exception:
        pass
    return {"approved": len(texts), "activated": out.get("activated"), "remaining": len(remain)}


def reject_pending_rules(
    *,
    indices: Optional[List[int]] = None,
    all: bool = False,
) -> Dict[str, Any]:
    pending = read_pending()
    if not pending:
        return {"rejected": 0, "message": "没有待拒绝规则"}
    if all:
        write_pending([])
        return {"rejected": len(pending), "message": "已清空待审规则"}
    if indices is None:
        return {"rejected": 0, "message": "需要 index 或 all=true"}
    remain = list(pending)
    removed = 0
    for i in sorted(indices, reverse=True):
        if 0 <= int(i) < len(remain):
            remain.pop(int(i))
            removed += 1
    write_pending(remain)
    return {"rejected": removed, "remaining": len(remain)}


def evolution_gate(
    metrics: Dict[str, Any],
    *,
    label: str = "",
) -> Dict[str, Any]:
    """After a run: keep pending rules only if we beat rolling baseline."""
    pending = read_pending()
    baseline = _rolling_baseline(window=8)
    _save_baseline(baseline)

    cur_floor = float(metrics.get("max_floor") or 0)
    cur_act = float(metrics.get("max_act") or 1)
    b_floor = float(baseline.get("median_max_floor") or 0)
    b_act = float(baseline.get("median_max_act") or 1)

    improved = (
        cur_act > b_act
        or (cur_act >= b_act and cur_floor >= b_floor + 2)
        or (baseline.get("n", 0) < 3 and cur_floor >= 8)
    )
    regressed = bool(pending) and baseline.get("n", 0) >= 3 and (
        cur_act < b_act or (cur_act <= b_act and cur_floor < b_floor - 3)
    )

    result: Dict[str, Any] = {
        "baseline": baseline,
        "metrics": metrics,
        "improved": improved,
        "regressed": regressed,
        "pending": len(pending),
    }

    if not pending:
        _bump_rule_scores(metrics, helped=improved)
        return result

    if improved:
        n = _promote_pending()
        result["gate"] = "promoted"
        result["promoted"] = n
        _bump_rule_scores(metrics, helped=True)
    elif regressed:
        _retire_pending()
        _rollback_strategy()
        result["gate"] = "rolled_back"
        _bump_rule_scores(metrics, helped=False)
    else:
        result["gate"] = "hold_pending"
        # keep pending for next run
    return result


def _bump_rule_scores(metrics: Dict[str, Any], *, helped: bool) -> None:
    data = read_registry()
    delta = 0.35 if helped else -0.15
    if metrics.get("max_act", 1) >= 2:
        delta += 0.25
    for r in data.get("rules") or []:
        if str(r.get("status")) != "active":
            continue
        r["runs_seen"] = int(r.get("runs_seen") or 0) + 1
        if helped:
            r["runs_helped"] = int(r.get("runs_helped") or 0) + 1
        r["score"] = round(max(0.0, float(r.get("score") or 0) + delta), 3)
    # retire bottom rules
    active = [r for r in data.get("rules") or [] if str(r.get("status")) == "active"]
    active.sort(key=lambda r: float(r.get("score") or 0))
    for r in active[:3]:
        if float(r.get("score") or 0) < -0.5:
            r["status"] = "retired"
    write_registry(data)


_LAST_FINALIZED = ""


def finalize_run(
    *,
    label: str,
    last_state: Optional[Dict[str, Any]] = None,
    llm_summary: str = "",
) -> Dict[str, Any]:
    """End of run: log metrics, run evolution gate."""
    global _RUN, _LAST_FINALIZED
    rid = str(_RUN.get("id") or "")
    if rid and rid == _LAST_FINALIZED:
        return {"skipped": True, "reason": "duplicate_finalize"}
    run = (last_state or {}).get("run") or {}
    metrics = {
        "run_id": _RUN.get("id") or _now_iso(),
        "ts": _now_iso(),
        "label": label,
        "max_floor": max(int(_RUN.get("max_floor", 0)), _floor(run)),
        "max_act": max(int(_RUN.get("max_act", 1)), _act(run)),
        "reward_sum": round(float(_RUN.get("reward_sum", 0)), 3),
        "steps": int(_RUN.get("steps", 0)),
        "fail_steps": int(_RUN.get("fail_steps", 0)),
        "registry_version": read_registry().get("version", 0),
    }
    if llm_summary:
        metrics["llm_summary"] = llm_summary[:400]

    append_result(metrics)
    if rid:
        _LAST_FINALIZED = rid
    gate = evolution_gate(metrics, label=label)

    stuck_act1 = (
        metrics["max_act"] <= 1
        and _rolling_baseline(window=12).get("median_max_floor", 0) < 45
        and len(read_results(15)) >= 6
    )
    if stuck_act1:
        propose_rule_changes(
            [
                "Act1 Boss前一层：优先营火回血/升级，不进事件房。",
                "Act1 末段 floor≥45：HP>55% 可走直线 Boss，少绕精英。",
                "Boss战：先叠够格挡再出重击；多段攻击留费防。",
            ],
            source="supervisor",
            force_activate=True,
        )

    _RUN = {"id": "", "reward_sum": 0.0, "steps": 0, "fail_steps": 0, "max_floor": 0, "max_act": 1}
    return {"metrics": metrics, "gate": gate}


def ranked_rules_for_prompt(*, limit: int = 12) -> List[str]:
    data = read_registry()
    active = [
        r
        for r in data.get("rules") or []
        if str(r.get("status") or "") == "active" and str(r.get("text") or "").strip()
    ]
    active.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    out: List[str] = []
    for r in active[:limit]:
        out.append(str(r["text"]).strip())
    if not out:
        from plugins.sts2.notes import read_strategy

        out = [str(x).strip() for x in (read_strategy().get("rules") or []) if str(x).strip()]
    return out[-limit:]


def evolution_summary_for_status() -> str:
    b = _rolling_baseline(window=8)
    last = read_results(3)
    pending = read_pending()
    lines = [
        f"进化基线: Act{b.get('median_max_act', 1):.0f} / 层{b.get('median_max_floor', 0):.0f} "
        f"(近{int(b.get('n', 0))}局)",
        f"待审规则: {len(pending)} 条",
    ]
    if last:
        r0 = last[-1]
        lines.append(
            f"上局: {r0.get('label')} Act{r0.get('max_act')} 层{r0.get('max_floor')} "
            f"reward={r0.get('reward_sum')}"
        )
    reg = read_registry()
    top = ranked_rules_for_prompt(limit=3)
    if top:
        lines.append("高分规则: " + " | ".join(t[:50] for t in top))
    return "\n".join(lines)


def note_act_cleared(act: int) -> None:
    """User reached next act — reinforce map/combat rules for that act."""
    if act == 1:
        propose_rule_changes(
            [
                "★ 已进入 Act2：HP<58% 禁精英；每 3 层至少一次营火。",
                "Act2 多怪战先集火最低血；Debuff 回合有威胁才防。",
            ],
            source="supervisor",
            force_activate=True,
        )
    elif act == 2:
        propose_rule_changes(
            ["★ 已进入 Act3：Boss 前优先营火；保留药水进 Boss。"],
            source="supervisor",
            force_activate=True,
        )


def bootstrap_evolution_store() -> Dict[str, Any]:
    """Seed registry from existing strategy.yaml once."""
    reg = read_registry()
    if reg.get("rules"):
        return {"bootstrapped": False}
    from plugins.sts2.notes import read_strategy

    texts = [str(r).strip() for r in (read_strategy().get("rules") or []) if str(r).strip()]
    if not texts:
        return {"bootstrapped": False}
    _activate_rules(texts, source="bootstrap")
    return {"bootstrapped": True, "count": len(texts)}


def extract_rules_from_text(text: str, *, max_rules: int = 3) -> List[str]:
    rules: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "下局：" in line or line.startswith("下局:"):
            rules.append(line.split("：", 1)[-1].split(":", 1)[-1].strip()[:200])
        elif line.startswith(("-", "•", "*")):
            body = line.lstrip("-•* ").strip()
            if len(body) > 12:
                rules.append(body[:200])
    return rules[:max_rules]
