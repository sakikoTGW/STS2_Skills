# STS2 × OpenClaw

OpenClaw consumes STS2 through the **same stdio MCP bridge** as other MCP clients.

## 1. Install bridge dependencies

```bash
pip install mcp
# or: pip install 'hermes-agent[mcp]'
```

Clone or install this repo so `scripts/sts2_mcp_bridge.py` exists.

## 2. Register MCP server

```bash
cd /path/to/hermes-agent-main
hermes sts2 integration-config --platform openclaw
```

Run the printed `openclaw mcp set sts2 '...'` command, or merge the JSON into `mcp.servers.sts2` in OpenClaw config.

Example shape:

```json
{
  "command": "/path/to/python",
  "args": ["/path/to/hermes-agent-main/scripts/sts2_mcp_bridge.py"],
  "env": {
    "STS2_MCP_BASE_URL": "http://127.0.0.1:15526",
    "STS2_HOME": "/home/you/.openclaw/sts2"
  }
}
```

## 3. Skill

Copy `skills/slay-the-spire-2/` into your OpenClaw workspace skills (e.g. `~/.openclaw/workspace/skills/`). Adjust paths if your install differs.

## 4. Play loop

1. Start STS2 with MCP mod.
2. Confirm `ping_mod` (or prefixed variant) succeeds.
3. Each turn: `get_game_state` → reason → `perform_action` once (repeat until `end_turn`).

OpenClaw does **not** use Hermes `sts2_get_state` names — use MCP tool names from step 2.

## 5. Migrating from Hermes

If you used `hermes claw migrate`, keep using `~/.hermes` or point `STS2_HOME` at `~/.openclaw/sts2` for a fresh OpenClaw-only data dir.
