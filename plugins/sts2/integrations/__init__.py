"""Host-platform integration helpers (Hermes, OpenClaw, AstrBot)."""

from plugins.sts2.integrations.mcp_config import (
    astrbot_mcp_block,
    generic_mcp_block,
    mcp_bridge_script,
    openclaw_mcp_set_command,
    openclaw_mcp_block,
    repo_root_from_plugin,
)

__all__ = [
    "astrbot_mcp_block",
    "generic_mcp_block",
    "mcp_bridge_script",
    "openclaw_mcp_set_command",
    "openclaw_mcp_block",
    "repo_root_from_plugin",
]
