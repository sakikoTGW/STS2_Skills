---
name: slay-the-spire-2
description: "Play STS2 via MCP; Act1-safe loop and full-run."
version: 1.0.0
author: Hermes Agent
license: MIT
tags: [gaming, sts2, ironclad, silent, defect, necrobinder, regent, openclaw]
platforms: [windows, macos, linux]
---

# Slay the Spire 2 (OpenClaw + MCP)

Drive **Slay the Spire 2** through the **sts2** MCP server (`ping_mod`). You are the strategist; call MCP tools each turn.

## Prerequisites

1. Game running with **STS2 MCP** mod.
2. OpenClaw `mcp.servers.sts2` points at `scripts/sts2_mcp_bridge.py` from the Hermes STS2 repo.
3. `ping_mod` returns success (tool name may be prefixed, e.g. `sts2_ping_mod`).
4. **Character (optional):** `~/.config/sts2/config.yaml` → `sts2.character: silent`, or `STS2_CHARACTER=defect`, or `sts2 autoplay study --character regent`. Default is Ironclad.

## Core loop

```text
get_game_state(format=summary)
→ plan in chat
→ perform_action(action=..., parameters={...})
→ repeat until run ends
```

Use **fresh** indices from each `get_game_state` — hand slots renumber after plays.

## MCP tool map

| MCP tool | Role |
|----------|------|
| `ping_mod` | Health check |
| `get_game_state` | Board snapshot (`format=summary`) |
| `perform_action` | One game action |
| `search_wiki` | Card/relic/enemy lookup |
| `observe_player_actions` | While user plays manually |
| `get_action_log` | Recent inferred actions |

## Act 1 rules (beginner)

| Situation | Rule |
|-----------|------|
| Map HP &lt; 50% | Avoid elites; prefer `?` / rest / monsters |
| Campfire visible, HP &lt; 75% | Prefer rest |
| Combat | Block before lethal incoming damage |
| Rewards | Claim all rewards, then proceed |
| Combat turn | Spend energy, then `end_turn` |

## Pitfalls

- Stale `card_index` after playing a card.
- `proceed` before claiming rewards.
- Calling `perform_action` without reading latest state.

## Verification

- Boss slain / Act transition visible in `get_game_state`.
- Optional marker file under `STS2_HOME` (e.g. `FULL_RUN_CLEARED.txt`) if your bridge writes it.
