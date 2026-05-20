"""Single source of truth for STS2 play-mode labels (TUI banner + get_state)."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MODE_CHAT_HAND = "chat_hand_play"
MODE_MOUNT = "mount_mode"
MODE_CHAT_THROUGH = MODE_MOUNT  # compat
MODE_AUTOPILOT_READY = "autopilot_ready"
MODE_AUTOPILOT_RUNNING = "autopilot_running"
MODE_AUTOPILOT_PAUSED = "autopilot_paused"
MODE_WATCH = "watch"
MODE_LEARN = "learn"

_WATCHER_STARTED = False


def auto_run_env_enabled() -> bool:
    return os.environ.get("HERMES_STS2_AUTO_RUN", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def user_asked_stop(text: str) -> bool:
    """User wants to halt autopilot (chat interrupt)."""
    s = (text or "").strip().lower()
    if not s:
        return False
    stops = (
        "停",
        "停止",
        "别打",
        "别打了",
        "不要打",
        "停下",
        "停代打",
        "停止代打",
        "stop autopilot",
        "stop sts2",
        "sts2 stop",
        "action=stop",
    )
    if s in stops or s.startswith("停") and len(s) <= 8:
        return True
    return any(k in s for k in stops if len(k) >= 2)


def try_stop_on_user_message(text: str) -> Dict[str, Any]:
    if not user_asked_stop(text):
        return {"stopped": False}
    from plugins.sts2.autoplay import get_controller

    ctrl = get_controller()
    st = ctrl.status()
    if not (st.get("studying") or st.get("running")):
        return {"stopped": False, "reason": "autopilot not active"}
    out = ctrl.stop()
    try:
        emit_mode_banner_to_tui(force=True)
    except Exception:
        pass
    return {"stopped": True, **out}


def resolve_sts2_mode() -> Dict[str, Any]:
    """Current mode snapshot for UI and tools."""
    from plugins.sts2.autoplay import get_controller
    from plugins.sts2.play_mode import (
        agent_play_mode,
        autopilot_active,
        mount_mode,
        llm_marathon_allowed,
        marathon_forbidden,
    )

    ctrl = get_controller()
    st = ctrl.status()
    ap = autopilot_active()
    paused = bool(st.get("paused"))
    watching = bool(st.get("watching"))
    learning = bool(st.get("learning"))

    if watching:
        mode_id = MODE_WATCH
    elif learning:
        mode_id = MODE_LEARN
    elif ap and paused:
        mode_id = MODE_AUTOPILOT_PAUSED
    elif ap:
        mode_id = MODE_AUTOPILOT_RUNNING
    elif llm_marathon_allowed():
        mode_id = MODE_AUTOPILOT_READY
    elif mount_mode():
        mode_id = MODE_MOUNT
    else:
        mode_id = MODE_CHAT_HAND

    # User-facing: only two play styles (+ rare watch/learn)
    titles = {
        MODE_AUTOPILOT_RUNNING: "后台代打",
        MODE_AUTOPILOT_PAUSED: "后台代打",
        MODE_AUTOPILOT_READY: "后台代打",
        MODE_MOUNT: "挂载模式",
        MODE_CHAT_HAND: "未挂载",
        MODE_WATCH: "旁观",
        MODE_LEARN: "学习",
    }
    autopilot_ready_sub = "说「开始代打」或 sts2_autoplay action=run"
    if auto_run_env_enabled() and mode_id == MODE_AUTOPILOT_READY:
        autopilot_ready_sub = "游戏连上后自动开打；说「停」可停"

    subtitles = {
        MODE_AUTOPILOT_RUNNING: "自动出牌中 · 说「停」结束",
        MODE_AUTOPILOT_PAUSED: "已暂停 · resume 继续 / stop 退出",
        MODE_AUTOPILOT_READY: autopilot_ready_sub,
        MODE_MOUNT: "边聊边打：主 Agent 连续 get_state→act 直到通关",
        MODE_CHAT_HAND: "请用 Launch-Hermes-STS2.bat 启动挂载模式",
        MODE_WATCH: "你在游戏里操作，Hermes 只解说",
        MODE_LEARN: "你操作，Hermes 提问记笔记",
    }
    controls: Dict[str, List[str]] = {
        MODE_AUTOPILOT_RUNNING: ["说「停」· pause|resume|hint"],
        MODE_AUTOPILOT_PAUSED: ["resume|stop"],
        MODE_AUTOPILOT_READY: ["action=run 或等游戏连上"],
        MODE_MOUNT: ["说「开打」· get_state→act · 说「停」"],
        MODE_CHAT_HAND: ["Launch-Hermes-STS2.bat"],
        MODE_WATCH: ["stop"],
        MODE_LEARN: ["stop|hint"],
    }

    out: Dict[str, Any] = {
        "mode_id": mode_id,
        "title": titles.get(mode_id, mode_id),
        "subtitle": subtitles.get(mode_id, ""),
        "controls": controls.get(mode_id, []),
        "goal": "FULL_RUN_CLEARED",
        "autopilot_active": ap,
        "autopilot_paused": paused,
        "agent_play_env": agent_play_mode(),
        "auto_run_env": auto_run_env_enabled(),
        "llm_autopilot_allowed": llm_marathon_allowed(),
        "mount_mode_env": mount_mode(),
        "marathon_forbidden": marathon_forbidden(),
        "autoplay_steps": st.get("steps"),
        "last_state_type": st.get("last_state_type"),
    }
    out["runs_until_victory"] = mode_id == MODE_AUTOPILOT_RUNNING
    out["one_shot_expected"] = mode_id in (
        MODE_AUTOPILOT_RUNNING,
        MODE_AUTOPILOT_PAUSED,
        MODE_MOUNT,
    ) or (auto_run_env_enabled() and mode_id == MODE_AUTOPILOT_READY)
    return out


def format_mode_banner(*, compact: bool = False) -> str:
    m = resolve_sts2_mode()
    if compact:
        return f"【STS2·{m['title']}】{m['subtitle'][:140]}"

    status = ""
    if m.get("autopilot_active"):
        status = (
            f" · 步数 {m.get('autoplay_steps') or 0}"
            f" · {m.get('last_state_type') or '?'}"
            + (" · 暂停" if m.get("autopilot_paused") else "")
        )
    ctrl = (m.get("controls") or [""])[0]
    lines = [
        "════════ STS2 ════════",
        f"模式: {m['title']}{status}",
        m["subtitle"],
        f"目标: {m['goal']} · {ctrl}",
        "══════════════════════",
    ]
    return "\n".join(lines)


def structured_mode_status() -> Dict[str, Any]:
    m = resolve_sts2_mode()
    return {
        **m,
        "banner": format_mode_banner(),
        "banner_compact": format_mode_banner(compact=True),
    }


def emit_mode_banner_to_tui(*, force: bool = False) -> bool:
    if os.environ.get("HERMES_TUI_STS2_BRIDGE", "").strip() in ("0", "false", "no"):
        return False
    m = resolve_sts2_mode()
    mode_id = str(m.get("mode_id") or "")
    if not force:
        if getattr(emit_mode_banner_to_tui, "_last_id", None) == mode_id:
            return False
        emit_mode_banner_to_tui._last_id = mode_id  # type: ignore[attr-defined]

    try:
        from plugins.sts2.tui_emit import emit_sts2_to_tui

        return bool(emit_sts2_to_tui(format_mode_banner()))
    except Exception:
        return False


def ensure_autoplay_running(*, reason: str = "") -> Dict[str, Any]:
    """Start background LLM autopilot if AUTO_RUN / user asked run. Safe to call often."""
    from plugins.sts2.play_mode import mount_mode

    if mount_mode():
        return {"skipped": True, "reason": "mount_mode (no background autopilot)"}
    if not auto_run_env_enabled() and reason != "user_run":
        return {"skipped": True, "reason": "HERMES_STS2_AUTO_RUN not set"}

    from plugins.sts2.play_mode import llm_marathon_allowed

    if not llm_marathon_allowed():
        return {"skipped": True, "reason": "llm_marathon not allowed"}

    from plugins.sts2.autoplay import get_controller

    ctrl = get_controller()
    st = ctrl.status()
    if st.get("studying") or st.get("running"):
        return {"skipped": True, "reason": "already running", "running": True}

    try:
        from plugins.sts2 import client as sts2_client

        sts2_client.ping()
    except Exception as exc:
        return {
            "skipped": True,
            "reason": "game not ready",
            "detail": str(exc)[:200],
            "will_retry": auto_run_env_enabled(),
        }

    out = ctrl.start_study(announce=True)
    emit_mode_banner_to_tui(force=True)
    if out.get("success"):
        return {"started": True, "reason": reason, **out}
    return {"started": False, "reason": reason, **out}


def start_auto_run_watcher() -> None:
    """Poll until game MCP is up, then start autopilot once (AUTO_RUN=1)."""
    global _WATCHER_STARTED
    if _WATCHER_STARTED or not auto_run_env_enabled():
        return
    _WATCHER_STARTED = True

    def _loop() -> None:
        interval = float(os.environ.get("HERMES_STS2_AUTO_RUN_POLL_SEC", "10"))
        max_min = float(os.environ.get("HERMES_STS2_AUTO_RUN_MAX_MIN", "120"))
        attempts = max(1, int(max_min * 60 / max(interval, 3)))
        for i in range(attempts):
            r = ensure_autoplay_running(reason="watcher")
            if r.get("started") or r.get("running"):
                return
            if r.get("reason") == "already running":
                return
            if not r.get("will_retry", True):
                return
            if i == 0 or i % 6 == 0:
                try:
                    from plugins.sts2.tui_emit import emit_sts2_to_tui

                    emit_sts2_to_tui(
                        "【STS2】等待游戏+Mod… 连上后自动一口气代打（说「停」可停）"
                    )
                except Exception:
                    pass
            time.sleep(interval)
        try:
            from plugins.sts2.tui_emit import emit_sts2_to_tui

            emit_sts2_to_tui(
                "【STS2】AUTO_RUN 超时未连上游戏。请先开 STS2+Mod，再说「开始代打」或 action=run"
            )
        except Exception:
            pass

    threading.Thread(target=_loop, name="sts2-auto-run-watcher", daemon=True).start()


def maybe_auto_start_autoplay() -> Dict[str, Any]:
    start_auto_run_watcher()
    return ensure_autoplay_running(reason="plugin_load")
