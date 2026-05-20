"""Slay the Spire 2 — STS2MCP HTTP tools, MCP bridge, autoplay, notes, ``hermes sts2`` CLI."""

from __future__ import annotations

import logging
from pathlib import Path

from plugins.sts2.autoplay import get_controller
from plugins.sts2.cli import register_cli as _register_sts2_cli
from plugins.sts2.cli import sts2_command as _sts2_command
from plugins.sts2.tools import (
    STS2_ACT_SCHEMA,
    STS2_AUTOPLAY_SCHEMA,
    STS2_GET_COMPENDIUM_SCHEMA,
    STS2_GET_PROFILE_SCHEMA,
    STS2_GET_STATE_SCHEMA,
    STS2_LEARN_SCHEMA,
    STS2_NOTE_SCHEMA,
    STS2_OBSERVE_SCHEMA,
    STS2_PING_SCHEMA,
    STS2_RECALL_SCHEMA,
    STS2_SETUP_STATUS_SCHEMA,
    STS2_WIKI_SEARCH_SCHEMA,
    _check_sts2_available,
    handle_sts2_act,
    handle_sts2_autoplay,
    handle_sts2_get_compendium,
    handle_sts2_get_profile,
    handle_sts2_get_state,
    handle_sts2_learn,
    handle_sts2_note,
    handle_sts2_observe,
    handle_sts2_ping,
    handle_sts2_recall,
    handle_sts2_setup_status,
    handle_sts2_wiki_search,
)

logger = logging.getLogger(__name__)

_SKILL_PATH = Path(__file__).resolve().parent / "references" / "playbook.md"

_TOOLS = (
    ("sts2_setup_status", STS2_SETUP_STATUS_SCHEMA, handle_sts2_setup_status, "🔧", None),
    ("sts2_ping", STS2_PING_SCHEMA, handle_sts2_ping, "🃏", _check_sts2_available),
    ("sts2_get_state", STS2_GET_STATE_SCHEMA, handle_sts2_get_state, "🎴", _check_sts2_available),
    ("sts2_act", STS2_ACT_SCHEMA, handle_sts2_act, "⚔️", _check_sts2_available),
    ("sts2_wiki_search", STS2_WIKI_SEARCH_SCHEMA, handle_sts2_wiki_search, "📖", _check_sts2_available),
    ("sts2_get_profile", STS2_GET_PROFILE_SCHEMA, handle_sts2_get_profile, "📊", _check_sts2_available),
    ("sts2_get_compendium", STS2_GET_COMPENDIUM_SCHEMA, handle_sts2_get_compendium, "📚", _check_sts2_available),
    ("sts2_autoplay", STS2_AUTOPLAY_SCHEMA, handle_sts2_autoplay, "🎮", None),
    ("sts2_recall", STS2_RECALL_SCHEMA, handle_sts2_recall, "🧠", None),
    ("sts2_learn", STS2_LEARN_SCHEMA, handle_sts2_learn, "🧬", None),
    ("sts2_observe", STS2_OBSERVE_SCHEMA, handle_sts2_observe, "👁️", _check_sts2_available),
    ("sts2_note", STS2_NOTE_SCHEMA, handle_sts2_note, "📝", None),
)


def _on_session_end(**kwargs) -> None:
    try:
        get_controller().stop()
    except Exception as exc:
        logger.debug("sts2 on_session_end: %s", exc)


def register(ctx) -> None:
    """Register STS2 tools (bundled backend plugin)."""

    def _emit_cast(line: str) -> None:
        text = line.strip()
        if not text:
            return
        try:
            from plugins.sts2.tui_emit import emit_sts2_to_tui

            if emit_sts2_to_tui(text):
                return
        except Exception:
            pass
        try:
            from hermes_cli.plugins import get_plugin_manager

            cli = get_plugin_manager()._cli_ref
            running = bool(cli and getattr(cli, "_agent_running", False))
        except Exception:
            running = False
        if not running:
            try:
                ctx.inject_message(f"[STS2] {text}")
                return
            except Exception:
                pass
        print(f"\n[STS2] {text}", flush=True)

    get_controller().set_emit(_emit_cast)

    try:
        from plugins.sts2.mode_display import emit_mode_banner_to_tui, maybe_auto_start_autoplay

        emit_mode_banner_to_tui(force=True)
        maybe_auto_start_autoplay()
    except Exception as exc:
        logger.debug("sts2 mode banner: %s", exc)

    for name, schema, handler, emoji, check_fn in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="sts2",
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            emoji=emoji,
        )

    ctx.register_cli_command(
        name="sts2",
        help="Slay the Spire 2 (STS2MCP setup, mod install, autoplay)",
        setup_fn=_register_sts2_cli,
        handler_fn=_sts2_command,
        description="Install and configure STS2MCP + Hermes sts2 tools/MCP/autoplay",
    )

    ctx.register_command(
        "sts2",
        handler=_slash_sts2,
        description="STS2 autoplay status/stop",
        args_hint="[status|stop|feed|watch|learn]",
    )

    ctx.register_hook("on_session_end", _on_session_end)

    if _SKILL_PATH.is_file():
        ctx.register_skill(
            "autoplay",
            _SKILL_PATH,
            description="Autoplay STS2 via API; per-turn commentary.",
        )


def _slash_sts2(args: str = "", **kwargs) -> str:
    ctrl = get_controller()
    parts = (args or "").strip().split()
    sub = parts[0].lower() if parts else "status"
    if sub in ("stop", "halt"):
        ctrl.stop()
        return "STS2 autoplay/watch stopped."
    if sub == "watch":
        out = ctrl.start_watch()
        return "STS2 watch started." if out.get("success") else str(out.get("error", out))
    if sub == "learn":
        out = ctrl.start_learn()
        return "STS2 学习模式已启动。" if out.get("success") else str(out.get("error", out))
    if sub == "feed":
        from plugins.sts2.storage import live_feed_path

        path = live_feed_path()
        if not path.is_file():
            return "No live feed yet."
        return path.read_text(encoding="utf-8")[-4000:]
    st = ctrl.status()
    return (
        f"STS2 autoplay running={st.get('running')} steps={st.get('steps')} "
        f"state={st.get('last_state_type')} paused={st.get('paused')}"
    )
