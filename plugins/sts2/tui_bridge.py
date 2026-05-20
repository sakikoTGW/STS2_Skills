"""Bridge STS2 autoplay commentary into Hermes TUI (same or separate process)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)

_BROADCAST = "tui_broadcast.jsonl"
_CONSUMER_STATE = "tui_broadcast_offset.json"
_WATCHDOG_STARTED = False
_LAST_RESUME_AT = 0.0
_RESUME_COOLDOWN_SEC = 45.0


def broadcast_path() -> Path:
    p = sts2_home() / _BROADCAST
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def broadcast_to_tui(text: str) -> bool:
    """Push commentary to TUI Activity (+ chat via gateway consumer)."""
    return deliver_to_tui(text)


def deliver_to_tui(text: str) -> bool:
    """Emit once with dedupe; jsonl fallback if gateway offline."""
    line = (text or "").strip()
    if not line:
        return False
    try:
        from plugins.sts2.tui_cast_dedupe import should_deliver

        if not should_deliver(line):
            return True
    except Exception:
        pass
    try:
        from plugins.sts2.tui_emit import emit_sts2_to_tui

        if emit_sts2_to_tui(line):
            return True
    except Exception as exc:
        logger.debug("emit_sts2_to_tui: %s", exc)
    row = {"ts": time.time(), "text": line[:4000]}
    try:
        with broadcast_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def _read_offset() -> int:
    path = sts2_home() / _CONSUMER_STATE
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("offset") or 0)
    except (OSError, json.JSONDecodeError, TypeError):
        return 0


def _write_offset(offset: int) -> None:
    path = sts2_home() / _CONSUMER_STATE
    try:
        path.write_text(json.dumps({"offset": offset}), encoding="utf-8")
    except OSError:
        pass


def _consume_broadcast_once() -> int:
    """Emit pending lines to all TUI sessions. Returns lines consumed."""
    path = broadcast_path()
    if not path.is_file():
        return 0
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    offset = _read_offset()
    if offset > len(raw):
        offset = 0
    chunk = raw[offset:]
    if not chunk.strip():
        return 0
    try:
        from tui_gateway import server as gw
    except ImportError:
        return 0
    sids = list(getattr(gw, "_sessions", {}).keys())
    if not sids:
        return 0
    lines = chunk.splitlines()
    consumed = 0
    pos = offset
    for line in lines:
        line = line.strip()
        if not line:
            pos += 1
            continue
        try:
            row = json.loads(line)
            text = str(row.get("text") or "").strip()
        except json.JSONDecodeError:
            text = line
        if not text:
            pos += len(line) + 1
            continue
        try:
            from plugins.sts2.tui_cast_dedupe import should_deliver

            if not should_deliver(text):
                pos += len(line) + 1
                continue
        except Exception:
            pass
        payload = {"text": text[:2000]}
        for sid in sids:
            try:
                gw._emit("sts2.commentary", sid, payload)  # noqa: SLF001
            except Exception:
                pass
        pos += len(line) + 1
        consumed += 1
    if consumed:
        _write_offset(pos)
    return consumed


def start_broadcast_consumer() -> None:
    """Daemon: tail tui_broadcast.jsonl → gateway sts2.commentary events."""
    global _WATCHDOG_STARTED
    if os.environ.get("HERMES_TUI_STS2_BRIDGE", "1").strip() in ("0", "false", "no"):
        return
    if getattr(start_broadcast_consumer, "_started", False):
        return
    start_broadcast_consumer._started = True  # type: ignore[attr-defined]

    def _loop() -> None:
        while True:
            try:
                _consume_broadcast_once()
            except Exception as exc:
                logger.debug("sts2 broadcast consumer: %s", exc)
            time.sleep(0.35)

    threading.Thread(target=_loop, name="sts2-tui-broadcast", daemon=True).start()


def maybe_start_sts2_from_tui() -> None:
    """TUI boot: never auto-start background autopilot; agent uses get_state + sts2_act."""
    if getattr(maybe_start_sts2_from_tui, "_started", False):
        return
    maybe_start_sts2_from_tui._started = True  # type: ignore[attr-defined]
    try:
        from plugins.sts2.manual_mode import set_manual_mode

        set_manual_mode(False)
    except Exception:
        pass

    def _boot() -> None:
        time.sleep(2.5)
        try:
            from hermes_cli.plugins import discover_plugins

            discover_plugins()
        except Exception as exc:
            logger.warning("sts2 tui: discover_plugins: %s", exc)
        try:
            from plugins.sts2.autoplay import get_controller

            ctrl = get_controller()
            if ctrl.status().get("studying") or ctrl.status().get("running"):
                ctrl.stop()
                deliver_to_tui(
                    "【STS2】已停止后台代打。请由主 Agent：get_state → 思考 → sts2_act 通关。"
                )
        except Exception as exc:
            logger.debug("sts2 tui boot stop autopilot: %s", exc)

    threading.Thread(target=_boot, name="sts2-tui-boot", daemon=True).start()


def _start_tui_watchdog() -> None:
    global _WATCHDOG_STARTED
    if _WATCHDOG_STARTED:
        return
    _WATCHDOG_STARTED = True

    def _loop() -> None:
        from plugins.sts2 import client as sts2_client
        from plugins.sts2.autoplay import get_controller
        from plugins.sts2.config import load_sts2_config

        cfg = load_sts2_config()
        stall_sec = float(cfg.get("supervisor_stall_seconds", 90))
        poll = float(cfg.get("supervisor_poll_seconds", 2.5))
        last_steps = -1
        last_progress = time.time()
        while True:
            try:
                ctrl = get_controller()
                status = ctrl.status()
                steps = int(status.get("steps") or 0)
                try:
                    from plugins.sts2.play_mode import autopilot_enabled

                    ap = autopilot_enabled()
                except Exception:
                    ap = False
                if ap:
                    if steps != last_steps:
                        last_steps = steps
                        last_progress = time.time()
                    elif time.time() - last_progress > stall_sec:
                        deliver_to_tui(
                            f"【STS2】自动打局 {stall_sec:.0f}s 无步进，检查游戏/MCP 是否卡住…"
                        )
                        last_progress = time.time()
                elif status.get("studying") or status.get("running"):
                    deliver_to_tui("【STS2】手操模式：正在停止误启动的后台打局…")
                    ctrl.stop()
                    last_progress = time.time()
                    last_steps = -1
            except Exception as exc:
                logger.debug("sts2 tui watchdog: %s", exc)
            time.sleep(poll)

    threading.Thread(target=_loop, name="sts2-tui-watchdog", daemon=True).start()


def forward_tui_message_to_coach(text: str) -> None:
    """User chat in TUI → coach_inbox (background autopilot reads next steps)."""
    if os.environ.get("HERMES_TUI_STS2_COACH", "1").strip() in ("0", "false", "no"):
        return
    raw = (text or "").strip()
    if not raw or raw.startswith("!"):
        return
    if raw.startswith("/sts2"):
        raw = raw[5:].strip() or raw
    try:
        from plugins.sts2.coach_channel import append_outbox, ensure_coach_files, inbox_path

        ensure_coach_files()
        stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        block = f"\n\n### TUI 留言 {stamp}\n{raw[:2000]}\n"
        with inbox_path().open("a", encoding="utf-8") as fh:
            fh.write(block)
        append_outbox(f"**TUI 已收到:** {raw[:400]}")
        broadcast_to_tui(f"【教练·TUI】已写入 inbox：{raw[:120]}")
        try:
            from plugins.sts2.manual_learn import record_coach_message

            cmd = record_coach_message(raw)
            if cmd and cmd.get("learn_command"):
                msg = cmd.get("message") or f"approved={cmd.get('approved')} rejected={cmd.get('rejected')}"
                append_outbox(f"**【学习】** {msg}")
                broadcast_to_tui(f"【学习】{msg[:160]}")
        except Exception:
            pass
    except Exception as exc:
        logger.debug("forward_tui_message_to_coach: %s", exc)
