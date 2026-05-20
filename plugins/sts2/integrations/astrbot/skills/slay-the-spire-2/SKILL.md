---
name: slay-the-spire-2
description: "Play STS2 via MCP; Act1-safe loop and full-run."
version: 1.0.0
author: Hermes Agent
license: MIT
tags: [gaming, sts2, ironclad, silent, defect, necrobinder, regent, astrbot]
platforms: [windows, macos, linux]
---

# Slay the Spire 2 (AstrBot + MCP)

Use the **sts2** MCP server configured in AstrBot WebUI. Tool names may appear with a server prefix in the agent UI.

## Prerequisites

1. STS2 running with MCP mod; API at `http://127.0.0.1:15526`.
2. AstrBot MCP entry: `python` + `scripts/sts2_mcp_bridge.py` + env `STS2_MCP_BASE_URL`, `STS2_HOME`.
3. `ping_mod` succeeds.
4. **Character (optional):** set `sts2.character` in `~/.config/sts2/config.yaml`, or env `STS2_CHARACTER` (e.g. `silent`), or CLI `sts2 autoplay study --character defect`.

## Core loop

```text
get_game_state(format=summary)
→ reply to user with plan
→ perform_action(...)
```

## Tools

| Tool | Role |
|------|------|
| `get_game_state` | `format=summary` for compact state |
| `perform_action` | `action` + optional `parameters` dict |
| `search_wiki` | Fuzzy card/relic search |
| `get_action_log` | Spectate / learning from human play |

## Act 1 heuristics

- Low HP: avoid elite map nodes.
- Combat: block before taking lethal hits.
- Rewards: claim everything before `proceed`.
- Same turn: multiple `perform_action` until out of energy, then `end_turn`.

## Pitfalls

- Reusing old hand indices.
- One action per turn while energy remains.
