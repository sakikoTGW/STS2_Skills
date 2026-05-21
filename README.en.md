# STS2_Skills

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**English** · [简体中文](README.md)

Agent tooling for **Slay the Spire 2** over [STS2MCP](https://github.com/Gennadiyev/STS2MCP). Exposes game state and actions to LLM hosts via native Hermes tools or a stdio [MCP](https://modelcontextprotocol.io/) server (OpenClaw, AstrBot, Cursor, and others).

**Latest release:** [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest)

## Features

- In-game STS2MCP HTTP API (`get_state`, `act`, wiki search)
- **Configurable starting character** for autoplay / new-run menus
- Bundled knowledge bases (mechanics, map flow, relics, wiki snapshots)
- Optional combat coaching, Act 1 guards, spectate / action logging
- **Hermes Agent**, **OpenClaw**, and **AstrBot** integrations

## Requirements

- Python 3.11+
- Slay the Spire 2 (Steam)
- [STS2MCP](https://github.com/Gennadiyev/STS2MCP) mod in singleplayer
- Game API default `http://127.0.0.1:15526` (configurable)

## Installation

### From a release archive

1. Download the latest `.zip` from [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest) (Windows GUI: **`sts2skill.exe`**).
2. Extract and open a shell in the project root.

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[mcp]"
```

Copy `config.example.yaml` to `~/.config/sts2/config.yaml` (Windows: `%USERPROFILE%\.config\sts2\config.yaml`), or merge `sts2:` into `~/.hermes/config.yaml` for Hermes.

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

### GUI installer (Windows)

Download **`sts2skill.exe`** from [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest), pick host (standalone / Hermes / OpenClaw / AstrBot), paths, and character. It unpacks STS2_Skills, installs the mod, and writes MCP + config.

CLI alternative: `python scripts/sts2_setup_wizard.py` or `sts2 install-wizard`.

Versioning: `1.0.x` patch line. Migrating from legacy **v1.3.0** / plugin **v2.x**: [VERSION_MIGRATION.md](VERSION_MIGRATION.md).

### Per-host setup

```bash
sts2 setup --host openclaw --install-mod
sts2 setup --host astrbot --install-mod
sts2 setup --host hermes --install-mod      # needs Hermes CLI; else writes ~/.hermes
sts2 setup --host standalone
python scripts/sts2_setup_wizard.py
```

### Manual steps

```bash
sts2 install-mod
# Launch game (singleplayer + mod on)
sts2 ping
sts2 status
```

### Autoplay with a chosen character

```bash
sts2 autoplay study --character 1
sts2 autoplay study -c silent
sts2 autoplay start -c 2
```

MCP config for third-party hosts:

```bash
sts2 integration-config --platform openclaw
sts2 integration-config --platform astrbot --json-only
```

Stdio MCP bridge:

```bash
sts2-mcp
# or: python scripts/sts2_mcp_bridge.py
```

## Configuration

| Variable / file | Purpose |
|-----------------|--------|
| `config.example.yaml` → `~/.config/sts2/config.yaml` | `base_url`, `character`, timeouts, autoplay |
| `STS2_MCP_BASE_URL` | Override API URL |
| `STS2_CHARACTER` | Session character (0–4 or name) |
| `STS2_HOME` | Runtime data (logs, strategy, trajectories) |
| `OPENCLAW_HOME` / `ASTRBOT_DATA` | Host-specific `…/sts2` defaults |

Defaults: `plugins/sts2/config.py`.

### Character selection

| Index | ID | Name |
|-------|-----|------|
| **0** | `IRONCLAD` | Ironclad |
| **1** | `SILENT` | Silent |
| **2** | `DEFECT` | Defect |
| **3** | `NECROBINDER` | Necrobinder |
| **4** | `REGENT` | Regent |

**Precedence:** `STS2_CHARACTER` → `sts2.character` in YAML → default **0** (Ironclad has the richest build/combat heuristics).

```yaml
sts2:
  character: 1
```

```bash
export STS2_CHARACTER=3
sts2 autoplay start --character 2
```

Confirm with `sts2 status` (e.g. `character: 1 (SILENT)`).

## Host integration

### Hermes Agent

```bash
hermes sts2 setup
hermes sts2 install-mod
hermes sts2 ping
```

Skill: `skills/slay-the-spire-2/`.

### OpenClaw

```bash
sts2 integration-config --platform openclaw
# or: sts2 setup --host openclaw --install-mod
```

See [OpenClaw integration](plugins/sts2/integrations/openclaw/README.md).

### AstrBot

AstrBot ≥ 3.5 with MCP ([docs](https://docs.astrbot.app/en/use/mcp.html)):

```bash
sts2 integration-config --platform astrbot --json-only
# or: sts2 setup --host astrbot --install-mod
```

See [AstrBot integration](plugins/sts2/integrations/astrbot/README.md).

## MCP tools

| Tool | Description |
|------|-------------|
| `ping_mod` | API health check |
| `get_game_state` | Snapshot (`format=summary` recommended) |
| `perform_action` | One game action |
| `search_wiki` | Card / relic lookup |
| `observe_player_actions` | Poll manual play |
| `get_action_log` | Recent inferred actions |

Hosts may prefix tool names (e.g. `sts2_get_game_state`).

## Layout

```
plugins/sts2/          # Core plugin, knowledge, host docs
scripts/               # MCP bridge, mod install
skills/                # Agent skill (slay-the-spire-2)
tests/
config.example.yaml
```

Runtime data lives under `STS2_HOME`, not in the repo.

## Development

```bash
pip install -e ".[mcp,dev]"
pytest
ruff check plugins scripts tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Wiki maintenance

```bash
sts2 sync-wiki --merge-yaml
sts2 crawl-wiki --integrate
```

Respect [wiki.gg](https://slaythespire.wiki.gg) terms. Do not commit cookies or API keys.

## License

MIT — see [LICENSE](LICENSE). Game assets and the STS2MCP mod are not included in this repository.


<p align="center">
  <img src="docs/images/readme-screenshot.jpg" alt="STS2 runtime preview" width="720">
</p>
