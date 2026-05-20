#!/usr/bin/env python3
"""Stdio MCP entrypoint for OpenClaw, AstrBot, Cursor, and other MCP clients.

Does not require the Hermes CLI — only the ``hermes-agent`` package (or repo on PYTHONPATH).

  python scripts/sts2_mcp_bridge.py

Environment:
  STS2_MCP_BASE_URL — STS2MCP HTTP API (default http://127.0.0.1:15526)
  STS2_HOME — runtime logs/strategy (default ~/.hermes/sts2, or platform-specific)
  OPENCLAW_HOME / ASTRBOT_DATA — optional; see plugins/sts2/platform_home.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plugins.sts2.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
