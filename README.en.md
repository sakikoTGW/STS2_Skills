# STS2_Skills

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**English** · [简体中文](README.md)

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
sts2 autoplay study --character silent
sts2 autoplay start -c defect
```

See [README.md](README.md) for full configuration (character selection, host integration, MCP tools).

## License

MIT — see [LICENSE](LICENSE).
