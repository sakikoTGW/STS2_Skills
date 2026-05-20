# STS2 Autoplay Playbook (plugin skill)

Load with `skill_view('sts2:autoplay')` or bundled `slay-the-spire-2`.

## Tools (native, preferred)

- `sts2_setup_status` — diagnose install before playing
- `sts2_get_state` → `sts2_act` — every turn
- `sts2_wiki_search` — card/relic text
- `sts2_get_profile` / `sts2_get_compendium` — meta progress

## MCP (optional)

If `mcp_servers.sts2` is enabled: `mcp_sts2_get_game_state`, `mcp_sts2_perform_action`, etc.
Prefer native `sts2_*` tools when both are available (same HTTP backend).

**OpenClaw / AstrBot:** use stdio MCP (`scripts/sts2_mcp_bridge.py`) — tools `get_game_state`, `perform_action`, …
See `plugins/sts2/integrations/` and `hermes sts2 integration-config`.

## Commentary (verbose)

Before each `sts2_act`, tell the user 2–4 sentences: situation, intent, planned action.
If you need a human choice (`ask_user_on`), ask and wait — do not act until answered.

## Autoplay

- `sts2_autoplay` action=start | stop | step | status | hint
- Commentary every step (verbose config)
- Reflect on combat end / game over → hot_notes + strategy.yaml
- Trajectories: `~/.hermes/sts2/trajectories/*.jsonl`

## Manual loop

1. `sts2_get_state` (json)
2. Short commentary
3. If user messaged you, answer first; `sts2_autoplay` hint if paused
4. `sts2_act` with indices from state only
5. Repeat until stop, game over, or user interrupt
