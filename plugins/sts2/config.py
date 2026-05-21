"""Load ``sts2`` settings from Hermes config + environment."""

from __future__ import annotations

import os
from typing import Any

from plugins.sts2.client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT

_DEFAULTS: dict[str, Any] = {
    "base_url": DEFAULT_BASE_URL,
    "timeout": DEFAULT_TIMEOUT,
    "autoplay": False,
    "autoplay_use_llm": False,
    "commentary": "verbose",
    "ask_user_on": ["card_reward", "relic_select", "relic_select_boss"],
    "pause_on_ask": True,
    "enable_mcp_on_setup": True,
    "max_repeat_state": 3,
    "step_interval_seconds": 0.55,
    "state_settle_min_seconds": 0.28,
    "state_settle_poll_seconds": 0.12,
    "state_settle_max_seconds": 2.8,
    "watch_interval_seconds": 0.65,
    "log_dir": "",
    "enforce_single_driver": True,
    "learn_mode_enabled": True,
    "study_reflect_use_llm": True,
    "study_marathon": False,
    "loop_runs": True,
    "apply_memory_each_step": True,
    "max_consecutive_failures": 25,
    "max_steps_per_run": 8000,
    "use_combat_scorer": False,
    "study_combat_rule_shortcuts": False,
    "study_combat_rule_fallback": False,
    "study_rules_fallback": False,
    "auto_curate_knowledge": True,
    "knowledge_use_llm": True,
    "max_wiki_per_step": 3,
    "supervisor_stall_seconds": 90,
    "supervisor_poll_seconds": 2.5,
    "study_use_llm": True,
    "study_llm_combat": True,
    "study_llm_max_tokens": 720,
    "study_llm_temperature": 0.3,
    "study_card_pick_llm": True,
    "study_card_pick_max_tokens": 720,
    "study_card_pick_temperature": 0.35,
    "study_card_pick_wiki_first": True,
    "study_card_pick_wiki_max_fetches": 6,
    "study_combat_play_llm": True,
    "study_combat_play_max_tokens": 900,
    "study_combat_play_temperature": 0.35,
    "study_combat_wiki_first": True,
    "study_combat_wiki_max_fetches": 6,
    "autopilot_until_victory": True,
    "study_show_full_thinking": True,
    "study_coach_channel": True,
    "study_write_thinking_trace": True,
    "manual_auto_learn": True,
    "agent_auto_learn": True,
    "llm_autopilot_enabled": True,
    "pause_autopilot_on_manual_act": True,
    "autopilot_attach_decision_brief": True,
    "act1_guard": "objective",
    "act1_guard_autopilot": "objective",
    "manual_learn_use_llm": True,
    "manual_skip_static_bootstrap": True,
    "manual_map_reflect": True,
    "combat_fsm_enabled": True,
    "combat_fsm_auto_think": True,
    "combat_fsm_think_min_interval": 0.85,
    "mount_fsm_deep_think": True,
    "mount_think_max_tokens": 1400,
    "mount_think_temperature": 0.32,
    "build_analyze_after_run": True,
    "build_analyze_use_llm": True,
    "auto_repair": False,
    "hermes_may_patch_code": False,
    "api_down_backoff_seconds": 8,
    "character": 0,
}

# Single source for driver-lock fallback when reading a partial cfg dict.
DEFAULT_ENFORCE_SINGLE_DRIVER = bool(_DEFAULTS["enforce_single_driver"])


def enforce_single_driver_enabled(cfg: dict[str, Any] | None = None) -> bool:
    """Whether MCP manual act must yield to autoplay/study driver lock."""
    if cfg is None:
        cfg = load_sts2_config()
    return bool(cfg.get("enforce_single_driver", DEFAULT_ENFORCE_SINGLE_DRIVER))


def load_sts2_config() -> dict[str, Any]:
    merged = dict(_DEFAULTS)
    raw: dict[str, Any] | None = None
    try:
        from hermes_cli.config import load_config

        section = load_config().get("sts2")
        if isinstance(section, dict):
            raw = section
    except Exception:
        pass
    if raw is None:
        try:
            from plugins.sts2.host_config import load_sts2_section

            section = load_sts2_section()
            if section:
                raw = section
        except Exception:
            pass
    if isinstance(raw, dict):
        merged.update(raw)

    env_url = (os.environ.get("STS2_MCP_BASE_URL") or "").strip()
    if env_url:
        merged["base_url"] = env_url.rstrip("/")

    from plugins.sts2.character_choice import (
        DEFAULT_CHARACTER,
        DEFAULT_CHARACTER_INDEX,
        resolve_character_setting,
    )

    char_env = (os.environ.get("STS2_CHARACTER") or "").strip()
    if char_env:
        idx, canon = resolve_character_setting(char_env)
    else:
        idx, canon = resolve_character_setting(merged.get("character"))
    merged["character_index"] = idx
    merged["character"] = canon
    merged.setdefault("character_index", DEFAULT_CHARACTER_INDEX)

    try:
        merged["timeout"] = float(merged.get("timeout", DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        merged["timeout"] = DEFAULT_TIMEOUT

    if merged.get("study_marathon"):
        try:
            merged["max_repeat_state"] = max(int(merged.get("max_repeat_state", 3)), 8)
        except (TypeError, ValueError):
            merged["max_repeat_state"] = 8
        try:
            merged["max_steps_per_run"] = max(int(merged.get("max_steps_per_run", 500)), 8000)
        except (TypeError, ValueError):
            merged["max_steps_per_run"] = 8000

    from plugins.sts2.autonomy import autopilot_until_victory, full_run_cleared

    if autopilot_until_victory(merged):
        merged["pause_on_ask"] = False
        merged["ask_user_on"] = []

    try:
        from plugins.sts2.play_mode import agent_play_mode, marathon_forbidden, mount_mode

        if agent_play_mode() or marathon_forbidden():
            merged["pause_on_ask"] = False
            merged["ask_user_on"] = []
            merged["use_combat_scorer"] = False
            merged["autopilot_until_victory"] = False
        if mount_mode():
            merged["combat_fsm_enabled"] = True
            merged["mount_fsm_deep_think"] = bool(merged.get("mount_fsm_deep_think", True))
            merged["combat_fsm_auto_think"] = False
        if agent_play_mode():
            # Main agent is the only brain — no substitute autopilot LLM path.
            if not mount_mode():
                merged["combat_fsm_auto_think"] = False
            merged["study_combat_play_llm"] = False
            merged["study_card_pick_llm"] = False
            merged["study_use_llm"] = False
            merged["study_combat_rule_fallback"] = False
            merged["study_rules_fallback"] = False
            merged["study_combat_rule_shortcuts"] = False
            # Wiki is mandatory context, not optional study-mode fluff.
            merged["study_combat_wiki_first"] = True
            merged["study_combat_wiki_max_fetches"] = max(
                int(merged.get("study_combat_wiki_max_fetches", 4)), 8
            )
            merged["agent_combat_wiki_max_fetches"] = max(
                int(merged.get("agent_combat_wiki_max_fetches", 12)), 12
            )
            merged["auto_curate_knowledge"] = True
    except Exception:
        pass

    return merged


def mcp_server_config() -> dict[str, Any]:
    """Stdio MCP server entry for ``mcp_servers.sts2`` in config.yaml."""
    import shutil
    import sys

    from plugins.sts2.integrations.mcp_config import mcp_bridge_script

    bridge = mcp_bridge_script()
    exe = shutil.which("sts2-mcp")
    if exe:
        command, args = exe, []
    elif bridge.is_file():
        command, args = sys.executable, [str(bridge)]
    else:
        command, args = sys.executable, ["-m", "plugins.sts2.mcp_server"]

    from plugins.sts2.integrations.mcp_config import generic_mcp_block, hermes_mcp_block
    from plugins.sts2.platform_home import detect_runtime_host

    host = detect_runtime_host()
    if host == "hermes":
        block = hermes_mcp_block()
    elif host in ("openclaw", "astrbot"):
        block = generic_mcp_block(platform=host)
    else:
        block = generic_mcp_block(platform="generic")

    return {
        "enabled": True,
        "command": command,
        "args": args,
        "env": block.get("env") or {
            "STS2_MCP_BASE_URL": str(load_sts2_config().get("base_url", DEFAULT_BASE_URL)),
        },
        "timeout": 120,
        "connect_timeout": 30,
    }
