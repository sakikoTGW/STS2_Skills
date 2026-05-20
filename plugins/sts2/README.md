# STS2 plugin (Slay the Spire 2)

Agent bridge for **Slay the Spire 2** via [STS2MCP](https://github.com/Gennadiyev/STS2MCP). Ships as a Hermes backend plugin and as a standalone package ([STS2_Skills](https://github.com/sakikoTGW/STS2_Skills)).

## Host platforms

| Platform | Integration | Skill |
|----------|-------------|-------|
| Hermes Agent | Native `sts2_*` tools + optional MCP | `skills/gaming/slay-the-spire-2` |
| OpenClaw | stdio MCP (`scripts/sts2_mcp_bridge.py`) | `integrations/openclaw/skills/` |
| AstrBot | MCP in WebUI | `integrations/astrbot/skills/` |

## Requirements

1. Slay the Spire 2 (Steam)
2. STS2MCP mod in `mods/` (`hermes sts2 install-mod` or `sts2 install-mod`)
3. Singleplayer with mod enabled; API at `http://127.0.0.1:15526` unless overridden

## Quick start (Hermes)

```bash
hermes sts2 setup
hermes sts2 install-mod
hermes sts2 ping
```

## Quick start (MCP hosts)

```bash
pip install mcp
sts2 integration-config --platform openclaw   # or astrbot, generic
sts2-mcp
```

See `integrations/` for per-host notes. Full standalone README: [STS2_Skills](https://github.com/sakikoTGW/STS2_Skills).

## Character selection

Autoplay and `run_flow` menu automation honor `sts2.character` (and `STS2_CHARACTER` / CLI `--character`).

| Setting | Example |
|---------|---------|
| `~/.config/sts2/config.yaml` | `character: silent` |
| Env | `STS2_CHARACTER=defect` |
| CLI | `sts2 autoplay study --character regent` |

Supported values: `ironclad`, `silent`, `defect`, `necrobinder`, `regent` (Chinese aliases like `猎手`, `机器人` also work). Implementation: `character_choice.py`.

Ironclad-specific build/combat playbooks remain in `ironclad_builds.py`; other characters fall back to generic scoring until dedicated guides are added.

## MCP tools

| Tool | Purpose |
|------|---------|
| `ping_mod` | API health |
| `get_game_state` | Snapshot (`format=summary`) |
| `perform_action` | One game action |
| `search_wiki` | Card / relic search |
| `observe_player_actions` | Spectate manual play |
| `get_action_log` | Action trace tail |

## Runtime data (`STS2_HOME`)

| Path | Content |
|------|---------|
| `action_log.md` | Spectate log |
| `strategy/` | Strategy YAML |
| `trajectories/` | Run JSONL |
| `knowledge/` | Synced wiki data |

Resolution: `sts2.log_dir` → `STS2_HOME` → `OPENCLAW_HOME/sts2` → `ASTRBOT_DATA/sts2` → `HERMES_HOME/sts2`.

## Knowledge base

Bundled under `references/`. Refresh with `hermes sts2 sync-wiki` / `crawl-wiki` (or `sts2` CLI subcommands in standalone installs).

Wiki-derived data is for personal automation only; respect source site terms. Do not commit `huiji_cookies.txt` or secrets.
