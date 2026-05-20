# STS2_Skills

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Agent tooling for **Slay the Spire 2** over [STS2MCP](https://github.com/Gennadiyev/STS2MCP). Exposes game state and actions to LLM hosts through native tools (Hermes Agent) or a stdio [MCP](https://modelcontextprotocol.io/) server (OpenClaw, AstrBot, Cursor, and others).

**Latest release:** [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest)

## Features

- HTTP bridge to the in-game STS2MCP API (`get_state`, `act`, wiki lookup)
- **Configurable playable character** for autoplay / new-run menus (not locked to Ironclad)
- Bundled knowledge bases (mechanics, map flow, relics, wiki crawl snapshots)
- Optional combat coaching, Act 1 policy guards, and spectate / action logging
- Host integrations for **Hermes Agent**, **OpenClaw**, and **AstrBot**

## Requirements

- Python 3.11+
- Slay the Spire 2 (Steam)
- [STS2MCP](https://github.com/Gennadiyev/STS2MCP) mod enabled in singleplayer
- Game API at `http://127.0.0.1:15526` (configurable)

## Installation

### From a release archive

1. Download the latest `.zip` from [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest).
2. Extract and open a shell in the project root.

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[mcp]"
```

Copy `config.example.yaml` to `~/.config/sts2/config.yaml` (Windows: `%USERPROFILE%\.config\sts2\config.yaml`), or merge the `sts2:` section into `~/.hermes/config.yaml` when using Hermes.

### From Git

```bash
git clone https://github.com/sakikoTGW/STS2_Skills.git
cd STS2_Skills
pip install -e ".[mcp]"
```

```bash
pip install "git+https://github.com/sakikoTGW/STS2_Skills.git[mcp]"
```

## Quick start

```bash
sts2 install-mod          # install STS2MCP into the game mods/ folder
# Launch the game (singleplayer, mod on)
sts2 ping                 # verify API connectivity
sts2 status               # shows base_url, character, autoplay flags
```

### Autoplay with a chosen character

```bash
# One-off (CLI flag)
sts2 autoplay study --character silent

# Persistent (config file — see below)
sts2 autoplay start -c defect
```

Generate MCP server config for third-party hosts:

```bash
sts2 integration-config --platform openclaw
sts2 integration-config --platform astrbot --json-only
```

Run the stdio MCP bridge directly:

```bash
sts2-mcp
# or: python scripts/sts2_mcp_bridge.py
```

## Configuration

| Variable / file | Purpose |
|-----------------|--------|
| `config.example.yaml` → `~/.config/sts2/config.yaml` | `base_url`, `character`, timeouts, autoplay flags |
| `STS2_MCP_BASE_URL` | Override API base (default `http://127.0.0.1:15526`) |
| `STS2_CHARACTER` | Override playable character for this shell session |
| `STS2_HOME` | Runtime data (logs, strategy, trajectories) |
| `OPENCLAW_HOME` / `ASTRBOT_DATA` | Optional host-specific defaults under `…/sts2` |

See `plugins/sts2/config.py` for the full default set.

### Character selection

When autoplay or menu automation starts a **new run**, the bridge picks the character you configure instead of always selecting Ironclad.

| Canonical ID | English | 中文常用名 |
|--------------|---------|------------|
| `IRONCLAD` | Ironclad | 铁甲战士 / 战士 |
| `SILENT` | Silent | 猎手 / 刺客 |
| `DEFECT` | Defect | 机器人 |
| `NECROBINDER` | Necrobinder | 死灵 / 亡灵 |
| `REGENT` | Regent | 储君 / 皇子 |

**Priority (highest wins):** `STS2_CHARACTER` env → `sts2.character` in YAML → default `IRONCLAD`.

**1. Config file** — copy `config.example.yaml` and set:

```yaml
sts2:
  character: silent   # ironclad | silent | defect | necrobinder | regent
```

Windows path: `%USERPROFILE%\.config\sts2\config.yaml`  
Hermes users can merge the same key under `sts2:` in `~/.hermes/config.yaml`.

**2. Environment variable**

```bash
# bash
export STS2_CHARACTER=necrobinder

# PowerShell
$env:STS2_CHARACTER = "regent"
```

**3. CLI** (sets `STS2_CHARACTER` for that command)

```bash
sts2 autoplay start --character defect
sts2 autoplay study -c silent
sts2 autoplay run --character regent --max-steps 500
```

Verify with `sts2 status` (prints `character: SILENT`, etc.).

> **Note:** Deck-building and combat heuristics are richest for **Ironclad** (`ironclad_builds.py`). Other characters use generic rules and wiki context; autoplay still works but may be weaker than a character-specific guide.

## Host integration

### Hermes Agent

```bash
hermes sts2 setup
hermes sts2 install-mod
hermes sts2 ping
```

Bundled skill: `skills/slay-the-spire-2/`. For a full Hermes checkout, this tree lives under `plugins/sts2/`.

### OpenClaw

```bash
sts2 integration-config --platform openclaw
```

Register the printed JSON with `openclaw mcp set sts2 '…'` or under `mcp.servers.sts2`. Skill template: `plugins/sts2/integrations/openclaw/skills/slay-the-spire-2/`.

### AstrBot

Requires AstrBot ≥ 3.5 with MCP ([docs](https://docs.astrbot.app/en/use/mcp.html)). Paste JSON from:

```bash
sts2 integration-config --platform astrbot --json-only
```

into the WebUI MCP settings. Details: `plugins/sts2/integrations/astrbot/README.md`.

## MCP tools

| Tool | Description |
|------|-------------|
| `ping_mod` | API health check |
| `get_game_state` | Snapshot (`format=summary` recommended) |
| `perform_action` | Execute one game action |
| `search_wiki` | Card / relic lookup |
| `observe_player_actions` | Poll manual play |
| `get_action_log` | Recent inferred action trace |

Hosts may prefix tool names (e.g. `sts2_get_game_state`); use the names listed in your MCP client.

## Project layout

```
plugins/sts2/          # core plugin, knowledge bases, host integration docs
scripts/               # MCP bridge, mod installer
skills/                # agent skill (slay-the-spire-2)
tests/                 # pytest suite
config.example.yaml    # sample configuration
```

Runtime data is written under `STS2_HOME` (not shipped in the repo).

## Development

```bash
pip install -e ".[mcp]"
pytest tests/ -q
```

To rebuild this standalone tree from the [hermes-agent](https://github.com/NousResearch/hermes-agent) monorepo:

```bash
python scripts/build_sts2_github_release.py --zip --github-user sakikoTGW
```

## Knowledge base maintenance

```bash
sts2 sync-wiki --merge-yaml
sts2 crawl-wiki --integrate
```

Bundled JSON under `plugins/sts2/references/` is derived from public wikis; respect [wiki.gg](https://slaythespire.wiki.gg) and third-party site terms. Do not commit cookies or API keys.

## License

MIT — see [LICENSE](LICENSE). Game assets and the STS2MCP mod are not included in this repository.
