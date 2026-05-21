"""Host-platform integration helpers (Hermes, OpenClaw, AstrBot)."""

from plugins.sts2.integrations.host_setup import (
    ENFORCE_SINGLE_DRIVER_BY_HOST,
    SetupResult,
    setup_host,
)
from plugins.sts2.integrations.mcp_config import (
    astrbot_mcp_block,
    generic_mcp_block,
    hermes_mcp_block,
    mcp_bridge_script,
    openclaw_mcp_block,
    openclaw_mcp_set_command,
    repo_root_from_plugin,
)
from plugins.sts2.platform_home import detect_runtime_host, resolve_sts2_home

__all__ = [
    "ENFORCE_SINGLE_DRIVER_BY_HOST",
    "SetupResult",
    "setup_host",
    "astrbot_mcp_block",
    "detect_runtime_host",
    "generic_mcp_block",
    "hermes_mcp_block",
    "mcp_bridge_script",
    "openclaw_mcp_set_command",
    "openclaw_mcp_block",
    "repo_root_from_plugin",
    "resolve_sts2_home",
]
