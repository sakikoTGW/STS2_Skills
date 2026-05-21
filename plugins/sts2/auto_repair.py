"""Runtime auto-repair + optional Hermes code-fix brief (user allows patch)."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from plugins.sts2.source_paths import plugin_source_dir
from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)

_REPAIR_BRIEF = "hermes_repair_brief.md"
_ALLOW_FLAG = "HERMES_MAY_FIX_STS2.code"


def repair_allowed() -> bool:
    from plugins.sts2.config import load_sts2_config

    if os.environ.get("HERMES_TUI_STS2_AUTO_REPAIR", "").strip() in ("1", "true", "yes"):
        return True
    return bool(load_sts2_config().get("auto_repair", False))


def may_patch_code() -> bool:
    from plugins.sts2.config import load_sts2_config

    if os.environ.get("HERMES_ALLOW_STS2_CODE_FIX", "").strip() in ("1", "true", "yes"):
        return True
    return bool(load_sts2_config().get("hermes_may_patch_code", False))


def attempt_auto_repair(
    kind: str,
    message: str,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply safe runtime fixes; optionally queue code-fix brief for Hermes."""
    if not repair_allowed():
        return {"skipped": True, "reason": "auto_repair disabled"}

    ctx = context or {}
    low = message.lower()
    repairs: list[str] = []

    if kind == "driver_busy" or "driver busy" in low:
        from plugins.sts2.program_health import _try_safe_heal

        if _try_safe_heal(kind, message, ctx):
            repairs.append("cleared_stale_locks")

    if kind in ("api_down", "exception") and (
        "cannot reach sts2mcp" in low
        or "connectionrefused" in low
        or "10061" in low
        or "10054" in low
        or "timed out" in low
    ):
        try:
            from plugins.sts2.autoplay import get_controller

            ctrl = get_controller()
            was_active = bool(
                ctrl.status().get("studying") or ctrl.status().get("running")
            )
            ctrl.stop()
            if was_active:
                repairs.append("stopped_study_until_api_back")
            ctrl._potion_fail_streak = 99  # noqa: SLF001
            repairs.append("blocked_auto_potion")
        except Exception as exc:
            logger.debug("api_down repair: %s", exc)
        repairs.append("waiting_for_game_api")

    if "unknown action: __wait__" in low:
        repairs.append("use_local_wait_skip")  # client.py handles __wait__ without POST

    if "no potion in slot" in low:
        try:
            from plugins.sts2.autoplay import get_controller

            get_controller()._potion_fail_streak = 3  # noqa: SLF001
            repairs.append("blocked_empty_potion_retries")
        except Exception:
            pass

    if "no proceed button" in low and ctx.get("state_type") == "bundle_select":
        repairs.append("bundle_select_use_confirm_bundle_selection")

    out: dict[str, Any] = {"repairs": repairs, "healed": bool(repairs)}

    if may_patch_code() and kind in ("exception", "api_down") and (
        "plugins/sts2" in str(ctx.get("traceback", ""))
        or kind == "exception"
    ):
        _write_code_repair_brief(kind, message, ctx, repairs)
        out["code_fix_brief"] = str(sts2_home() / _REPAIR_BRIEF)

    return out


def _write_code_repair_brief(
    kind: str,
    message: str,
    ctx: dict[str, Any],
    repairs: list[str],
) -> None:
    home = sts2_home()
    allow = home / _ALLOW_FLAG
    brief = home / _REPAIR_BRIEF
    try:
        allow.write_text(
            f"allowed_at={datetime.now(UTC).isoformat()}\n"
            f"Hermes/TUI agent may edit {plugin_source_dir()} "
            "to fix STS2 plugin bugs. Restart TUI after patch.\n",
            encoding="utf-8",
        )
        lines = [
            f"# STS2 待修 · {datetime.now(UTC).isoformat()}\n\n",
            f"- 插件源码: `{plugin_source_dir()}`\n",
            f"- 运行时目录 (`STS2_HOME`): `{home}`\n\n",
            f"- kind: {kind}\n",
            f"- message: {message[:800]}\n",
            f"- 已做运行时自愈: {', '.join(repairs) or '无'}\n\n",
        ]
        tb = str(ctx.get("traceback") or "")
        if tb:
            lines.append("## traceback\n\n```\n" + tb[-3500:] + "\n```\n")
        act = ctx.get("action")
        if act:
            lines.append(f"\naction: `{json.dumps(act, ensure_ascii=False)}`\n")
        st = ctx.get("state_type")
        if st:
            lines.append(f"state_type: `{st}`\n")
        brief.write_text("".join(lines), encoding="utf-8")
    except OSError as exc:
        logger.debug("write repair brief: %s", exc)


def wait_for_api(*, max_wait_sec: float = 90, poll_sec: float = 3.0) -> bool:
    """Block until STS2MCP ping ok (marathon resume helper)."""
    import time

    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        try:
            from plugins.sts2 import client as c

            if c.ping().get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(poll_sec)
    return False


def resume_study_if_configured() -> dict[str, Any]:
    """No-op — rule marathon permanently disabled."""
    return {"skipped": True, "reason": "rule_marathon_permanently_disabled"}
