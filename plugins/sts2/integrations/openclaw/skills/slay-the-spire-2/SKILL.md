---
name: slay-the-spire-2
description: "通过 MCP 游玩 STS2；第一层安全循环与通关。"
version: 1.0.0
author: Hermes Agent
license: MIT
tags: [gaming, sts2, ironclad, silent, defect, necrobinder, regent, openclaw]
platforms: [windows, macos, linux]
---

# 杀戮尖塔 2（OpenClaw + MCP）

通过 **sts2** MCP 服务器（`ping_mod`）驱动游戏。你是唯一决策者；每回合调用 MCP 工具。

## 前置条件

1. 游戏运行且开启 **STS2 MCP** 模组。
2. OpenClaw 的 `mcp.servers.sts2` 指向本仓库的 `scripts/sts2_mcp_bridge.py`。
3. `ping_mod` 成功（名称可能带前缀，如 `sts2_ping_mod`）。
4. **角色（可选）：** `sts2.character` 为 **0–4**（0 铁甲战士、1 静默猎手、2 故障机器人、3 亡灵契约师、4 储君），默认 0。

## 核心循环

```text
get_game_state(format=summary)
→ 在对话中规划
→ perform_action(action=..., parameters={...})
→ 重复直至本局结束
```

每次 `get_game_state` 后使用**最新**索引——出牌后手牌槽位会重排。

## MCP 工具

| 工具 | 作用 |
|------|------|
| `ping_mod` | 健康检查 |
| `get_game_state` | 局面快照（`format=summary`） |
| `perform_action` | 一个游戏操作 |
| `search_wiki` | 查卡牌 / 遗物 / 敌人 |
| `observe_player_actions` | 用户手动游玩时 |
| `get_action_log` | 近期推断操作 |

## 第一层规则（新手）

| 情况 | 规则 |
|------|------|
| 地图血量 &lt; 50% | 避精英；优先 `?` / 营火 / 普通战 |
| 地图可见营火且血量 &lt; 75% | 优先休息 |
| 战斗 | 致死伤害前先格挡 |
| 奖励 | 领完再 `proceed` |
| 战斗回合 | 用完能量再 `end_turn` |

## 常见错误

- 出牌后仍用旧的 `card_index`。
- 奖励未领就 `proceed`。
- 未读最新状态就 `perform_action`。

## 验证

- `get_game_state` 可见 Boss 击杀 / 层过渡。
- 若桥接写入，可选检查 `STS2_HOME` 下的 `FULL_RUN_CLEARED.txt`。
