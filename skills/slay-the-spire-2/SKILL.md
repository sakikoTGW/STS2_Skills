---
name: slay-the-spire-2
description: "Play STS2 via API; Act1-safe loop and full-run."
version: 2.0.0
author: Hermes Agent
license: MIT
tags: [gaming, sts2, ironclad, silent, defect, necrobinder, regent]
platforms: [windows, macos, linux]
metadata.hermes.category: gaming
metadata.hermes.config:
  - sts2.base_url
  - sts2.character
---

# Slay the Spire 2 Skill

Drive **Slay the Spire 2** through STS2MCP (`hermes sts2 ping`). **You** are the only strategist; the plugin only observes, blocks objective mistakes, and on **Act 1** applies a guaranteed-clear policy so a beginner can finish the first act.

## When to Use

- User wants a full run (`FULL_RUN_CLEARED`) or Act 1 clear
- Game open, singleplayer; character matches config or is already in an active run

## Prerequisites

1. Game running with **STS2 MCP** mod enabled.
2. `sts2_ping` returns ok.
3. **角色（可选）**：在 `~/.hermes/config.yaml` 的 `sts2.character` 设为 `ironclad` / `silent` / `defect` / `necrobinder` / `regent`，或 `set STS2_CHARACTER=silent`。终端代打：`hermes sts2 autoplay study --character silent`（若 CLI 已透传）。默认仍为铁甲战士；其它角色策略库较薄，Agent 需更多 wiki/自行推理。
4. 启动 `Launch-Hermes-STS2.bat`（**挂载模式**：边聊边打至通关）。
5. **怪物知识库**（首次）：`hermes sts2 sync-wiki --merge-yaml`（灰机 wiki 需浏览器 cookies 时用 `--cookies`；或 `--html-dir` 导入已保存 HTML）。仓库已内置 Act1 种子，无网也能读【怪物Wiki】。

## How to Run

### Core loop (required)

```text
sts2_get_state(summary=true)
→ Read agent_contract, play_brief, combat_fsm, survival_snapshot
→ Write thinking in chat (intents, net damage, map choice)
→ sts2_act ONE action
→ Repeat until FULL_RUN_CLEARED
```

**挂载模式**：`sts2_get_state(summary=true)` 含 **五区状态机** + `combat_think` 辅脑深度分析；`think_required` 时在聊天写清六项思考再 `sts2_act`。禁止 `sts2_autoplay run`。

### Act 1 beginner rules (you must follow even without coercion)

| Situation | Rule |
|-----------|------|
| Map HP &lt; 50% | Never `elite`; pick `?` / campfire / monster |
| Map floor ≤12, HP &lt; 72% | Avoid elite |
| Campfire on map, HP &lt; 75% | Prefer rest (heal) |
| Combat high damage turn | Block with all energy before attacking |
| 花园幽灵鳗 elite | Read 【怪物Wiki】 Skittish: first hit each turn gains Block (stacks); multi-hit same turn |
| Combat planning | Read **行为循环** line: `T+1≈X伤` uses strength + loop index; block before total exceeds HP |
| Rewards screen | `claim_reward` all (gold first), then `proceed` |
| Event | `choose_event_option` / `advance_dialogue`, never `menu_select` |
| Combat same turn | Multiple `sts2_act` until energy 0, then `end_turn` |

On Act 1, `validate_action` may **rewrite** map/rewards/rest mistakes (`act1_guard=objective`; combat stays LLM unless `full`). Check `action_corrected` / `act1_policy_applied`.

## Quick Reference

| Tool | Role |
|------|------|
| `sts2_get_state(summary=true)` | Observation + play_brief + FSM |
| `sts2_act` | Execute one action (Act1 policy may correct) |
| `sts2_wiki_search` | Card/enemy lookup (MCP) |
| `hermes sts2 sync-wiki` | Refresh local monster KB from 灰机 wiki |
| `sts2_autoplay action=run` | Start LLM autopilot until victory |
| `sts2_autoplay action=pause\|resume\|stop\|hint` | Control autopilot |

## Procedure

### New run

`sts2_ping` → `sts2_get_state` → `sts2_act`（`setup_status` 最多一次）。挂载模式不要用 terminal 写 HTTP。

若需**自动开新局并选角色**：配置 `sts2.character` 后使用 `sts2_autoplay action=study`（或 CLI `sts2 autoplay study -c <角色>`）；菜单阶段会 `menu_select` 对应角色，勿手动假定铁甲战士。

### Until Act 1 Boss dies

Follow table above; after each combat read rewards brief before `proceed`.

### Act 2–3

Same loop; Act1 auto-coercion stops when `run.act` &gt; 1. You carry full-run strategy.

## Pitfalls

- Guessing `card_index` — always re-`get_state` after each act.
- `proceed` with unclaimed rewards.
- One `sts2_act` per turn then stopping while energy remains.
- Trusting old hand indices after a play.

## Verification

- `HERMES_HOME/sts2/FULL_RUN_CLEARED.txt` after Act3 boss
- Act 1: boss room cleared, Act 2 map or victory transition in `get_state`
