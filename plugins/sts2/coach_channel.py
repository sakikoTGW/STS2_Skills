"""Two-way coach channel while marathon study runs (no pause required)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugins.sts2.storage import sts2_home

_INBOX = "coach_inbox.md"
_OUTBOX = "coach_outbox.md"
_THINKING = "thinking_trace.md"
_STATE = "coach_state.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def inbox_path() -> Path:
    p = sts2_home() / _INBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def outbox_path() -> Path:
    p = sts2_home() / _OUTBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def thinking_path() -> Path:
    p = sts2_home() / _THINKING
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def state_path() -> Path:
    return sts2_home() / _STATE


def ensure_coach_files() -> None:
    """Create inbox/outbox templates if missing."""
    inbox = inbox_path()
    if not inbox.is_file():
        inbox.write_text(
            "# 给 Hermes 留言（后台代打不会停，下几步会读到）\n\n"
            "在下面写你的建议或问题，保存即可。不要删本行说明。\n\n"
            "--- 从这里写 ---\n\n",
            encoding="utf-8",
        )
    out = outbox_path()
    if not out.is_file():
        out.write_text(
            "# Hermes 回复 / 确认\n\n"
            "（自动更新：收到留言后在这里写「已读 + 将怎么做」）\n\n",
            encoding="utf-8",
        )
    think = thinking_path()
    if not think.is_file():
        think.write_text(
            "# STS2 逐步思考过程\n\n"
            "每步决策的完整 commentary（模型/规则）都会追加在这里。\n"
            "用编辑器打开本文件或 `Get-Content -Wait` 实时看。\n\n",
            encoding="utf-8",
        )


def _read_state() -> Dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return {"inbox_offset": 0, "last_reply_ts": ""}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"inbox_offset": 0, "last_reply_ts": ""}


def _write_state(data: Dict[str, Any]) -> None:
    try:
        state_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _extract_user_block(text: str, offset: int) -> tuple[str, int]:
    """Text after marker or after offset; skip boilerplate headers."""
    marker = "--- 从这里写 ---"
    if marker in text:
        body = text.split(marker, 1)[-1].strip()
    else:
        body = text[offset:].strip() if offset else text.strip()
    lines: List[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#") and not lines:
            continue
        if s in ("---", "***"):
            continue
        lines.append(line)
    return "\n".join(lines).strip(), len(text)


def poll_coach_hint() -> str:
    """Return new user text since last poll (consumed)."""
    ensure_coach_files()
    path = inbox_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    st = _read_state()
    offset = int(st.get("inbox_offset") or 0)
    if offset > len(raw):
        offset = 0
    hint, new_offset = _extract_user_block(raw, offset)
    if not hint or hint == st.get("last_hint_consumed"):
        return ""
    st["inbox_offset"] = new_offset
    st["last_hint_consumed"] = hint
    st["last_poll_ts"] = _now()
    _write_state(st)
    return hint[:2000]


def append_outbox(message: str) -> None:
    ensure_coach_files()
    block = f"\n## {_now()}\n\n{message.strip()}\n"
    try:
        with outbox_path().open("a", encoding="utf-8") as fh:
            fh.write(block)
    except OSError:
        pass


def acknowledge_hint(hint: str, *, state_type: str = "", floor: int = 0) -> None:
    if not hint.strip():
        return
    append_outbox(
        f"**已读你的留言**（{state_type or '?'} 第{floor}层）\n\n"
        f"> {hint.strip()[:500]}\n\n"
        "下几步决策会把它当作 user_hint 注入模型/规则，**不会暂停后台代打**。"
    )


def append_thinking(
    *,
    commentary: str,
    action: Dict[str, Any],
    state_type: str = "",
    floor: int = 0,
    act: int = 1,
    user_hint: str = "",
) -> None:
    """Full reasoning log — always written in study mode."""
    ensure_coach_files()
    act_name = str(action.get("action") or "?")
    extra = ""
    if "card_index" in action:
        extra = f" card={action['card_index']}"
    lines = [
        f"\n### {_now()} · Act{act} 第{floor}层 · {state_type}\n\n",
    ]
    if user_hint:
        lines.append(f"**你的留言（本步）:** {user_hint[:300]}\n\n")
    if commentary.strip():
        lines.append(commentary.strip() + "\n\n")
    lines.append(f"**执行:** `{act_name}{extra}`\n")
    try:
        with thinking_path().open("a", encoding="utf-8") as fh:
            fh.writelines(lines)
    except OSError:
        pass


def coach_paths_summary() -> str:
    h = sts2_home()
    return (
        f"留言: `{h / _INBOX}`\n"
        f"回复: `{h / _OUTBOX}`\n"
        f"思考: `{h / _THINKING}`"
    )
