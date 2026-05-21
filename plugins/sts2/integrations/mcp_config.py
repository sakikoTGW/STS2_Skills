"""Generate stdio MCP server definitions for OpenClaw, AstrBot, and other MCP clients."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def repo_root_from_plugin() -> Path:
    return Path(__file__).resolve().parents[3]


def mcp_bridge_script(*, repo_root: Path | None = None) -> Path:
    root = repo_root or repo_root_from_plugin()
    return root / "scripts" / "sts2_mcp_bridge.py"


def _default_sts2_home(platform: str) -> str:
    from plugins.sts2.platform_home import resolve_sts2_home

    if platform == "openclaw":
        os.environ.setdefault(
            "OPENCLAW_HOME",
            str(resolve_openclaw_home()),
        )
    elif platform == "astrbot":
        os.environ.setdefault(
            "ASTRBOT_DATA",
            str(resolve_astrbot_data_dir()),
        )
    return str(resolve_sts2_home())


def resolve_openclaw_home(explicit: str = "") -> Path:
    from plugins.sts2.platform_home import resolve_openclaw_home as _resolve

    return _resolve(explicit)


def resolve_astrbot_data_dir(explicit: str = "") -> Path:
    from plugins.sts2.platform_home import resolve_astrbot_data_dir as _resolve

    return _resolve(explicit)


def _mcp_env(
    *,
    platform: str,
    base_url: str,
    sts2_home: str | None,
    astrbot_data: str | None = None,
    openclaw_home: str | None = None,
) -> dict[str, str]:
    from plugins.sts2.character_choice import resolve_character_setting

    home_path = Path(sts2_home or _default_sts2_home(platform))
    env: dict[str, str] = {
        "STS2_MCP_BASE_URL": base_url.rstrip("/"),
        "STS2_HOME": str(home_path),
    }
    cfg_file = home_path / "config.yaml"
    if cfg_file.is_file():
        env["STS2_CONFIG_PATH"] = str(cfg_file)

    if platform == "openclaw":
        oc = (openclaw_home or os.environ.get("OPENCLAW_HOME") or "").strip()
        if not oc:
            oc = str(resolve_openclaw_home())
        env["OPENCLAW_HOME"] = oc
    elif platform == "astrbot":
        data = (astrbot_data or os.environ.get("ASTRBOT_DATA") or "").strip()
        if not data:
            data = str(resolve_astrbot_data_dir())
        env["ASTRBOT_DATA"] = data

    char_raw = (os.environ.get("STS2_CHARACTER") or "").strip()
    if not char_raw:
        try:
            from plugins.sts2.host_config import load_sts2_section

            char_raw = str(load_sts2_section().get("character", ""))
        except Exception:
            char_raw = ""
    if char_raw:
        try:
            idx, _ = resolve_character_setting(char_raw)
            env["STS2_CHARACTER"] = str(idx)
        except Exception:
            env["STS2_CHARACTER"] = char_raw.strip()

    return env


def generic_mcp_block(
    *,
    platform: str = "generic",
    repo_root: Path | None = None,
    python: str | None = None,
    base_url: str | None = None,
    sts2_home: str | None = None,
    astrbot_data: str | None = None,
    openclaw_home: str | None = None,
) -> dict[str, Any]:
    """Stdio MCP block (OpenAI/Cursor/AstrBot WebUI/OpenClaw ``mcp.servers`` shape)."""
    from plugins.sts2.client import DEFAULT_BASE_URL
    from plugins.sts2.config import load_sts2_config

    cfg_url = str(load_sts2_config().get("base_url", DEFAULT_BASE_URL))
    bridge = mcp_bridge_script(repo_root=repo_root)
    py = python or sys.executable
    return {
        "command": py,
        "args": [str(bridge)],
        "env": _mcp_env(
            platform=platform,
            base_url=base_url or cfg_url,
            sts2_home=sts2_home,
            astrbot_data=astrbot_data,
            openclaw_home=openclaw_home,
        ),
    }


def openclaw_mcp_block(**kwargs: Any) -> dict[str, Any]:
    return generic_mcp_block(platform="openclaw", **kwargs)


def astrbot_mcp_block(**kwargs: Any) -> dict[str, Any]:
    return generic_mcp_block(platform="astrbot", **kwargs)


def hermes_mcp_block(**kwargs: Any) -> dict[str, Any]:
    return generic_mcp_block(platform="hermes", **kwargs)


def openclaw_mcp_set_command(**kwargs: Any) -> str:
    """Shell command for ``openclaw mcp set sts2 '<json>'``."""
    block = openclaw_mcp_block(**kwargs)
    payload = json.dumps(block, ensure_ascii=False)
    return f'openclaw mcp set sts2 {json.dumps(payload, ensure_ascii=False)}'


def format_integration_doc(platform: str, **kwargs: Any) -> str:
    bridge = mcp_bridge_script(repo_root=kwargs.get("repo_root"))
    block = generic_mcp_block(platform=platform, **kwargs)
    lines = [
        f"# STS2 MCP — {platform}",
        "",
        f"Bridge script: `{bridge}`",
        f"Game API (STS2MCP): `{block['env']['STS2_MCP_BASE_URL']}`",
        f"Runtime data: `{block['env']['STS2_HOME']}`",
        "",
        "## MCP server JSON",
        "",
        "```json",
        json.dumps(block, indent=2, ensure_ascii=False),
        "```",
    ]
    if platform == "openclaw":
        lines.extend(
            [
                "",
                "## OpenClaw CLI",
                "",
                "```bash",
                openclaw_mcp_set_command(**kwargs),
                "```",
                "",
                "Or add under `mcp.servers.sts2` in OpenClaw config.",
                "Skill: `plugins/sts2/integrations/openclaw/skills/slay-the-spire-2/`.",
            ]
        )
    elif platform == "astrbot":
        lines.extend(
            [
                "",
                "## AstrBot WebUI",
                "",
                "Settings → MCP → Add server → paste the JSON above.",
                "Python env: `pip install mcp`.",
                "",
                "Skill: `plugins/sts2/integrations/astrbot/skills/slay-the-spire-2/`.",
                "Star plugin (optional): `integrations/astrbot/plugin/`.",
            ]
        )
    elif platform == "hermes":
        lines.extend(
            [
                "",
                "## Hermes",
                "",
                "`hermes sts2 setup` — enables native `sts2_*` tools and `mcp_servers.sts2`.",
                "Skill: `skills/slay-the-spire-2/`.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## MCP tools (server name `sts2`)",
                "",
                "- `ping_mod` — health check",
                "- `get_game_state` — snapshot (format=summary|json|markdown)",
                "- `perform_action` — one game action",
                "- `search_wiki` — card/relic lookup",
                "- `observe_player_actions` / `get_action_log` — spectate manual play",
            ]
        )
    return "\n".join(lines) + "\n"
