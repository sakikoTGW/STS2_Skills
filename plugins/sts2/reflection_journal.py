"""Visible cross-run reflection — written to sts2/reflections.md + live_feed."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugins.sts2.storage import sts2_home


def reflections_path() -> Path:
    p = sts2_home() / "reflections.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def runner_status_path() -> Path:
    p = sts2_home() / "STATUS.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def append_reflection(
    *,
    label: str,
    floor: int,
    rule: str,
    llm_summary: str = "",
    actions_tail: str = "",
    extra_rules: Optional[List[str]] = None,
) -> None:
    """Append a human-readable reflection block (always, even without LLM)."""
    lines = [
        f"\n## {_now()} · {label} · 第{floor}层\n",
        f"**写入策略:** {rule}\n",
    ]
    if actions_tail:
        lines.append(f"**末几步:** {actions_tail}\n")
    if llm_summary.strip():
        lines.append(f"\n### Hermes 复盘\n{llm_summary.strip()}\n")
    if extra_rules:
        lines.append("\n### 提炼规则\n")
        for r in extra_rules:
            lines.append(f"- {r}\n")

    path = reflections_path()
    try:
        if not path.is_file():
            path.write_text(
                "# STS2 跨局反思日志\n\n"
                "督导代打每次阵亡/通关都会追加一节。最新在上。\n"
                "策略同步写入 `strategy/strategy.yaml`，每步注入【本局记忆】。\n\n",
                encoding="utf-8",
            )
        with path.open("a", encoding="utf-8") as fh:
            fh.writelines(lines)
    except OSError:
        pass


def read_last_reflection_summary(*, max_chars: int = 400) -> str:
    path = reflections_path()
    if not path.is_file():
        return "(尚无反思记录)"
    try:
        text = path.read_text(encoding="utf-8")
        parts = text.split("\n## ")
        if len(parts) < 2:
            return text[-max_chars:]
        last = "## " + parts[-1]
        return last[:max_chars].strip()
    except OSError:
        return "(读取失败)"


def format_reflection_cast(refl: Dict[str, Any]) -> str:
    """One loud line for live_feed."""
    if not refl.get("reflected") and not refl.get("recorded"):
        return ""
    label = str(refl.get("label") or "outcome")
    floor = refl.get("floor", "?")
    rule = str(refl.get("rule") or "").strip()
    summary = str(refl.get("summary") or refl.get("llm_summary") or "").strip()
    acts = str(refl.get("actions_tail") or "").strip()

    if label in ("game_over", "death", "run_end"):
        head = f"【反思·跨局】第{floor}层阵亡/结束"
    elif label == "combat_win":
        head = f"【反思·战斗】第{floor}层胜利"
    else:
        head = f"【反思】{label}"

    parts = [head]
    if summary:
        parts.append(summary[:500])
    elif rule:
        parts.append(rule[:280])
    if acts and label in ("game_over", "death", "run_end"):
        parts.append(f"末几步: {acts[:200]}")
    evo = refl.get("evolution") or {}
    gate = (evo.get("gate") or {}) if isinstance(evo.get("gate"), dict) else {}
    if gate.get("gate"):
        parts.append(f"进化门禁: {gate.get('gate')}")
    parts.append("→ 全文见 Hermes/sts2/reflections.md · 指标见 evolution/results.jsonl")
    return "\n".join(parts)


def write_runner_status(
    *,
    supervisor_msg: str = "",
    study_running: bool = False,
    study_steps: int = 0,
    game_state: Optional[dict] = None,
) -> None:
    """Single file the user can open to see auto-run + last reflection."""
    lines = [
        f"# STS2 自动跑状态 · {_now()}\n\n",
        f"- **督导:** {supervisor_msg or '—'}\n",
        f"- **后台代打 study:** {'运行中' if study_running else '未运行'}"
        f"（步数 {study_steps}）\n",
    ]
    if isinstance(game_state, dict):
        run = game_state.get("run") or {}
        p = game_state.get("player") or {}
        lines.append(
            f"- **游戏:** Act{run.get('act', '?')} 第{run.get('floor', '?')}层 "
            f"HP {p.get('hp', '?')}/{p.get('max_hp', '?')} "
            f"界面={game_state.get('state_type')}\n"
        )
    lines.append(f"\n## 最近反思\n\n{read_last_reflection_summary(max_chars=600)}\n")
    try:
        from plugins.sts2.evolution_loop import evolution_summary_for_status

        lines.append(f"\n## 进化闭环\n\n{evolution_summary_for_status()}\n")
    except Exception:
        pass
    try:
        from plugins.sts2.program_health import issues_summary_for_status

        lines.append(f"\n## {issues_summary_for_status()}\n")
    except Exception:
        pass
    lines.append(
        "\n## 看思考 / 和 Hermes 说话\n\n"
        f"- **逐步思考:** `{sts2_home() / 'thinking_trace.md'}`（每步完整 commentary）\n"
        f"- **你留言:** `{sts2_home() / 'coach_inbox.md'}`（保存后下几步生效，不暂停）\n"
        f"- **她回复:** `{sts2_home() / 'coach_outbox.md'}`\n"
        f"- 实况简版: `{sts2_home() / 'live_feed.md'}`\n"
    )
    lines.append(
        "\n## 文件\n\n"
        f"- 反思全文: `{reflections_path()}`\n"
        f"- 策略规则: `{sts2_home() / 'strategy' / 'strategy.yaml'}`\n"
        f"- 进化指标: `{sts2_home() / 'evolution' / 'results.jsonl'}`\n"
        f"- 程序问题: `{sts2_home() / 'PROGRAM_ISSUES.md'}`\n"
        f"- 结局历史: `{sts2_home() / 'run_history.jsonl'}`\n"
    )
    try:
        runner_status_path().write_text("".join(lines), encoding="utf-8")
    except OSError:
        pass


def extract_rules_from_reflection(text: str, *, max_rules: int = 3) -> List[str]:
    """Pull bullet lines from LLM postmortem into strategy.yaml."""
    rules: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "候选：" in line or line.startswith("候选:"):
            body = line.split("候选：", 1)[-1].split("候选:", 1)[-1].strip()
            if len(body) > 12:
                rules.append(body[:200])
            continue
        if line.startswith(("-", "•", "*")):
            body = line.lstrip("-•* ").strip()
            if len(body) > 12 and "下局：" not in body[:8]:
                rules.append(body[:200])
        elif line.startswith(("1.", "2.", "3.")) and len(line) > 10:
            rules.append(line[3:].strip()[:200])
        if len(rules) >= max_rules:
            break
    return rules
