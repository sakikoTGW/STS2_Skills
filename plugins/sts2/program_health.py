"""Detect STS2 program issues, report with fix hints, optional safe self-heal."""

from __future__ import annotations

import json
import logging
import re
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)

_ISSUES_JSONL = "program_issues.jsonl"
_ISSUES_MD = "PROGRAM_ISSUES.md"
_RECENT_FP: dict[str, float] = {}
_CAST_FP: dict[str, float] = {}
_DEDUPE_SEC = 120.0
_CAST_DEDUPE_SEC = 45.0


def issues_path() -> Path:
    return sts2_home() / _ISSUES_JSONL


def issues_md_path() -> Path:
    return sts2_home() / _ISSUES_MD


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _fingerprint(kind: str, message: str) -> str:
    import hashlib

    raw = f"{kind}:{message[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def report_issue(
    kind: str,
    message: str,
    *,
    severity: str = "warning",
    context: dict[str, Any] | None = None,
    fix_hint: str = "",
    fingerprint: str = "",
) -> dict[str, Any]:
    """Append issue for Hermes / human to fix. Returns row + whether self-heal ran."""
    import time

    fp = fingerprint or _fingerprint(kind, message)
    now = time.time()
    if fp in _RECENT_FP and now - _RECENT_FP[fp] < _DEDUPE_SEC:
        return {"skipped": True, "fingerprint": fp}
    _RECENT_FP[fp] = now

    row = {
        "ts": datetime.now(UTC).isoformat(),
        "kind": kind,
        "severity": severity,
        "message": message[:2000],
        "fix_hint": fix_hint[:1500],
        "fingerprint": fp,
        "context": context or {},
        "healed": False,
    }

    healed = _try_safe_heal(kind, message, context or {})
    repair_out: dict[str, Any] = {}
    try:
        from plugins.sts2.auto_repair import attempt_auto_repair

        repair_out = attempt_auto_repair(kind, message, context=context or {})
        if repair_out.get("healed") or repair_out.get("repairs"):
            healed = True
    except Exception as exc:
        logger.debug("auto_repair: %s", exc)
    row["healed"] = healed
    row["repairs"] = repair_out.get("repairs") or []

    path = issues_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("program_health write: %s", exc)

    _refresh_issues_md(row)
    _maybe_cast(row)
    return row


def report_exception(exc: BaseException, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    tb = traceback.format_exc()
    msg = f"{type(exc).__name__}: {exc}"
    fix = _suggest_fix_from_traceback(tb, str(exc))
    kind = "exception"
    sev = "error"
    if "driver busy" in msg.lower():
        kind = "driver_busy"
        from plugins.sts2.platform_home import resolve_sts2_home

        lock = resolve_sts2_home() / ".autoplay.lock"
        fix = fix or (
            "结束重复督导/study 进程；运行 scripts/Start-STS2-Supervisor-Singleton.ps1；"
            f"删除 {lock}（无进程占用时）。"
        )
    elif "ConnectionRefused" in type(exc).__name__ or "连接" in msg:
        kind = "api_down"
        sev = "critical"
        fix = fix or "启动杀戮尖塔 2 + CommunicationMod，确认 config.yaml 中 sts2.base_url。"
    return report_issue(
        kind,
        msg,
        severity=sev,
        context={**(context or {}), "traceback": tb[-4000:]},
        fix_hint=fix,
    )


def report_action_failure(error: str, action: dict[str, Any], state: dict[str, Any]) -> None:
    err = str(error or "").strip()
    if not err:
        return
    if "unknown action: __wait__" in err.lower():
        return
    fix = "检查 action_validate 与当前 state_type 是否匹配；敌人回合勿 end_turn。"
    if "hand_select" in err.lower() or "hand_select" in str(action.get("action", "")):
        fix = "hand_select 界面应 combat_select_card + combat_confirm_selection，勿 play_card。"
    if "invalid" in err.lower() and "card" in err.lower():
        fix = "card_index 越界：用 visibility 里手牌列表重选索引。"
    report_issue(
        "action_failure",
        err,
        severity="warning",
        context={
            "action": action,
            "state_type": state.get("state_type"),
            "floor": (state.get("run") or {}).get("floor"),
        },
        fix_hint=fix,
    )


def scan_controller_errors(errors: list[str]) -> None:
    for err in errors[-5:]:
        if not err:
            continue
        report_issue("autoplay_error", err, severity="warning", fix_hint="见 errors.log / 督导重启 study。")


def issues_summary_for_status(*, max_lines: int = 5) -> str:
    path = issues_path()
    if not path.is_file():
        return "程序健康: 无上报记录"
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-max_lines:]:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return "程序健康: 读取失败"
    if not rows:
        return "程序健康: 无上报记录"
    bits = []
    for r in rows[-max_lines:]:
        bits.append(f"- [{r.get('severity')}] {r.get('kind')}: {str(r.get('message', ''))[:80]}")
    return "程序健康 (最近):\n" + "\n".join(bits)


def _suggest_fix_from_traceback(tb: str, msg: str) -> str:
    if "read_last_reflection_summary" in tb and "positional" in msg:
        return "reflection_journal.read_last_reflection_summary 应用 max_chars= 关键字参数。"
    if "plugins\\sts2" in tb or "plugins/sts2" in tb:
        m = re.search(r'File "([^"]+plugins/sts2/[^"]+)", line (\d+)', tb)
        if m:
            return f"修复 STS2 插件: {m.group(1)}:{m.group(2)} — 见 PROGRAM_ISSUES.md 与 agent-transcript。"
    if "ModuleNotFoundError" in msg:
        return "依赖缺失: 在项目 venv 中 pip install -e . 后重试。"
    return "把 PROGRAM_ISSUES.md 与 traceback 交给 Cursor/Hermes 修代码后重启督导。"


def _try_safe_heal(kind: str, message: str, context: dict[str, Any]) -> bool:
    """Only non-destructive recovery (stale locks)."""
    low = message.lower()
    if kind != "driver_busy" and "driver busy" not in low:
        return False
    try:
        from plugins.sts2.process_lock import clear_stale_lock, release
        from plugins.sts2.storage import sts2_home

        for name in (".autoplay.lock", ".supervisor.lock"):
            lock = sts2_home() / name
            if clear_stale_lock(lock):
                release()
        from plugins.sts2 import driver_lock

        driver_lock.release("autoplay")
        return True
    except Exception as exc:
        logger.debug("self_heal failed: %s", exc)
        return False


def _refresh_issues_md(latest: dict[str, Any]) -> None:
    lines = [
        f"# STS2 程序问题上报 · {_now()}\n\n",
        "Hermes 自动发现插件/驱动/API 异常。请把本节交给 Cursor 修复代码。\n\n",
        "## 最新\n\n",
        f"- **类型:** {latest.get('kind')}\n",
        f"- **级别:** {latest.get('severity')}\n",
        f"- **信息:** {latest.get('message', '')[:500]}\n",
        f"- **建议修复:** {latest.get('fix_hint', '—')}\n",
        f"- **已尝试自愈:** {'是' if latest.get('healed') else '否'}\n",
        f"\n完整日志: `{issues_path()}`\n\n",
        "## 最近条目\n\n",
    ]
    try:
        path = issues_path()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines()[-12:]:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    lines.append(
                        f"- {_now()[:10]} **{r.get('kind')}** "
                        f"{str(r.get('message', ''))[:100]}\n"
                    )
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    try:
        issues_md_path().write_text("".join(lines), encoding="utf-8")
    except OSError:
        pass


def _maybe_cast(row: dict[str, Any]) -> None:
    if row.get("severity") not in ("error", "critical"):
        return
    import time

    fp = str(row.get("fingerprint") or row.get("kind") or "issue")
    now = time.time()
    if fp in _CAST_FP and now - _CAST_FP[fp] < _CAST_DEDUPE_SEC:
        return
    _CAST_FP[fp] = now

    repairs = row.get("repairs") or []
    try:
        from plugins.sts2.autoplay import get_controller

        ctrl = get_controller()
        if repairs and row.get("kind") == "api_down":
            ctrl._cast(  # noqa: SLF001
                f"【自愈】API 断开 → {', '.join(repairs)}。请启动游戏+mod，"
                "恢复后代打会自动续跑。"
            )
            return
        hint = str(row.get("fix_hint") or "")[:200]
        brief = sts2_home() / "hermes_repair_brief.md"
        extra = ""
        if brief.is_file():
            extra = "\n→ Hermes 可直改 plugins/sts2（见 hermes_repair_brief.md）"
        ctrl._cast(  # noqa: SLF001
            f"【程序问题·{row.get('kind')}】{str(row.get('message', ''))[:120]}\n"
            f"修复: {hint}{extra}"
        )
    except Exception:
        pass
