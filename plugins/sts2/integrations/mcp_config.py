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
    home = Path.home()
    if platform == "openclaw":
        oc = (os.environ.get("OPENCLAW_HOME") or "").strip()
        base = Path(oc).expanduser() if oc else home / ".openclaw"
        return str(base / "sts2")
    if platform == "astrbot":
        data = (os.environ.get("ASTRBOT_DATA") or "").strip()
        base = Path(data).expanduser() if data else home / "AstrBot" / "data"
        return str(base / "sts2")
    from hermes_constants import display_hermes_home

    return f"{display_hermes_home()}/sts2"


def _mcp_env(*, platform: str, base_url: str, sts2_home: str | None) -> dict[str, str]:
    env: dict[str, str] = {
        "STS2_MCP_BASE_URL": base_url.rstrip("/"),
        "STS2_HOME": sts2_home or _default_sts2_home(platform),
    }
    if platform == "openclaw":
        oc = (os.environ.get("OPENCLAW_HOME") or "").strip()
        if oc:
            env["OPENCLAW_HOME"] = oc
    if platform == "astrbot":
        data = (os.environ.get("ASTRBOT_DATA") or "").strip()
        if data:
            env["ASTRBOT_DATA"] = data
    return env


def generic_mcp_block(
    *,
    platform: str = "generic",
    repo_root: Path | None = None,
    python: str | None = None,
    base_url: str | None = None,
    sts2_home: str | None = None,
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
        ),
    }


def openclaw_mcp_block(**kwargs: Any) -> dict[str, Any]:
    return generic_mcp_block(platform="openclaw", **kwargs)


def astrbot_mcp_block(**kwargs: Any) -> dict[str, Any]:
    return generic_mcp_block(platform="astrbot", **kwargs)


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
                "Enable the bundled skill from `plugins/sts2/integrations/openclaw/skills/`.",
            ]
        )
    elif platform == "astrbot":
        lines.extend(
            [
                "",
                "## AstrBot WebUI",
                "",
                "Settings → MCP → Add server → paste the JSON above.",
                "",
                "Requires AstrBot ≥ 3.5 with MCP enabled. Install `mcp` in the same Python env:",
                "`pip install mcp` (or `pip install 'hermes-agent[mcp]'`).",
                "",
                "Bundle skill: copy `plugins/sts2/integrations/astrbot/skills/slay-the-spire-2/`",
                "into your AstrBot `data/plugins/<your-plugin>/skills/` or workspace skills folder.",
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
