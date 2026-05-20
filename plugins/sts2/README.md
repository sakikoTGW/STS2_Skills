# STS2 plugin (Slay the Spire 2)

Bridge [STS2MCP](https://github.com/Gennadiyev/STS2MCP) into AI agents. Supports **three host platforms**:

| Platform | Integration | Skill |
|----------|-------------|-------|
| **Hermes Agent** | Native `sts2_*` tools + optional MCP | `skills/gaming/slay-the-spire-2` |
| **OpenClaw** | MCP stdio via `scripts/sts2_mcp_bridge.py` | `integrations/openclaw/skills/` |
| **AstrBot** | MCP stdio (WebUI → MCP servers) | `integrations/astrbot/skills/` |

## Prerequisites (all platforms)

1. **Slay the Spire 2** installed (Steam).
2. **STS2MCP** mod in the game `mods/` folder (`hermes sts2 install-mod` on Hermes; or see [STS2MCP releases](https://github.com/Gennadiyev/STS2MCP)).
3. Game running in **singleplayer** with the mod enabled.
4. HTTP API reachable at `http://127.0.0.1:15526` (override with `STS2_MCP_BASE_URL`).

## Quick start — Hermes

```bash
hermes sts2 setup
hermes sts2 install-mod
hermes sts2 ping
```

Enable skill `slay-the-spire-2`. Mount mode: `Launch-Hermes-STS2.bat` (Windows).

## Quick start — OpenClaw

From this repo root (or after `pip install hermes-agent`):

```bash
pip install mcp
hermes sts2 integration-config --platform openclaw
```

Copy the JSON into OpenClaw (`openclaw mcp set sts2 '...'`) or `mcp.servers.sts2`.

Install skill: copy `plugins/sts2/integrations/openclaw/skills/slay-the-spire-2` to your OpenClaw skills directory.

Set runtime data (optional):

```bash
export OPENCLAW_HOME=~/.openclaw
export STS2_HOME=$OPENCLAW_HOME/sts2
```

## Quick start — AstrBot

AstrBot ≥ 3.5 with MCP support ([docs](https://docs.astrbot.app/en/use/mcp.html)):

```bash
pip install mcp
hermes sts2 integration-config --platform astrbot --json-only
```

Paste into **WebUI → MCP → Add server**.

```bash
export ASTRBOT_DATA=/path/to/AstrBot/data
export STS2_HOME=$ASTRBOT_DATA/sts2
```

Copy `integrations/astrbot/skills/slay-the-spire-2` into a plugin `skills/` folder or your workspace skills.

## MCP tools (shared by OpenClaw / AstrBot / Cursor)

| Tool | Purpose |
|------|---------|
| `ping_mod` | API health |
| `get_game_state` | Snapshot (`format=summary` recommended) |
| `perform_action` | One action (`play_card`, `end_turn`, …) |
| `search_wiki` | Card/relic search |
| `observe_player_actions` | Spectate manual play |
| `get_action_log` | Recent action trace |

Host agents may prefix tools (e.g. `sts2_ping_mod`). Use the name shown in your MCP tool list.

## Runtime data layout (`STS2_HOME`)

| Path | Content |
|------|---------|
| `action_log.md` | Spectate / inferred plays |
| `strategy/` | Learned strategy YAML |
| `trajectories/` | Run JSONL logs |
| `knowledge/` | Synced wiki / enemies (optional) |

Resolution order: `sts2.log_dir` in config → `STS2_HOME` → `OPENCLAW_HOME/sts2` → `ASTRBOT_DATA/sts2` → `HERMES_HOME/sts2`.

## Knowledge base

Bundled under `references/` (mechanics_kb, game_flow_kb, wiki_crawl). Refresh:

```bash
hermes sts2 sync-wiki --merge-yaml
hermes sts2 crawl-wiki --integrate
```

## License / data

Wiki-derived JSON is for personal automation; respect [wiki.gg](https://slaythespire.wiki.gg) and 灰机 wiki terms. Do not commit `huiji_cookies.txt` or API keys.
