# STS2 × AstrBot

[AstrBot MCP](https://docs.astrbot.app/en/use/mcp.html) (v3.5+) can attach the STS2 stdio server from this repo.

## 1. Dependencies

- Game + [STS2MCP](https://github.com/Gennadiyev/STS2MCP) mod
- `pip install mcp` in the **same Python environment as AstrBot**
- This repository (or `pip install hermes-agent` for `plugins.sts2`)

## 2. WebUI configuration

```bash
hermes sts2 integration-config --platform astrbot --json-only
```

In AstrBot WebUI → **MCP** → add server → paste JSON:

- **command**: your Python executable
- **args**: `["/absolute/path/to/scripts/sts2_mcp_bridge.py"]`
- **env**: `STS2_MCP_BASE_URL`, `STS2_HOME`

Example `STS2_HOME` when AstrBot data lives at `~/AstrBot/data`:

```json
"STS2_HOME": "/home/you/AstrBot/data/sts2"
```

Or set `ASTRBOT_DATA=/home/you/AstrBot/data` in the server env block.

## 3. Skill (optional)

Copy `skills/slay-the-spire-2/` into:

- `AstrBot/data/plugins/<your-plugin>/skills/slay-the-spire-2/`, or
- a workspace skills folder your agent reads.

Reload the plugin / skill manager in WebUI.

## 4. Character selection

Add to `~/.config/sts2/config.yaml` or the MCP `env` block:

```yaml
sts2:
  character: necrobinder
```

Values: `ironclad`, `silent`, `defect`, `necrobinder`, `regent`. Used when `sts2 autoplay` drives menu / new-run flow. Details: root [README](../../../../README.md#character-selection).

## 5. Tool names

AstrBot lists MCP tools with a server prefix. Typical loop:

1. `get_game_state` with `format=summary`
2. `perform_action` with `action` + `parameters`
3. `search_wiki` when you need card text

## 6. AstrBot-only plugin (alternative)

You do **not** need a custom Star plugin if MCP is enough. For a native AstrBot plugin that bundles HTTP tools without MCP, track [issue/discussion in your fork] — MCP is the supported cross-platform path today.
