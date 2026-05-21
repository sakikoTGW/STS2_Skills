---
name: slay-the-spire-2
description: "通过 MCP 游玩 STS2；第一层安全循环与通关。"
version: 1.0.3
author: Hermes Agent
license: MIT
tags: [gaming, sts2, ironclad, silent, defect, necrobinder, regent, astrbot]
platforms: [windows, macos, linux]
---

# 杀戮尖塔 2（AstrBot + MCP）

使用在 AstrBot WebUI 中配置的 **sts2** MCP 服务器。界面中的工具名可能带服务器前缀。

## 前置条件

1. STS2 已运行且开启 MCP 模组；API 为 `http://127.0.0.1:15526`。
2. AstrBot MCP 项：`python` + `scripts/sts2_mcp_bridge.py` + env `STS2_MCP_BASE_URL`、`STS2_HOME`。
3. `ping_mod` 调用成功。
4. **角色（可选）：** `config.yaml` 中 `character: 0–4`（0 铁甲战士 … 4 储君），或 `STS2_CHARACTER` / `sts2 autoplay study -c 1`。

## 核心循环

```text
get_game_state(format=summary)
→ 向用户说明计划
→ perform_action(...)
```

## 工具

| 工具 | 作用 |
|------|------|
| `get_game_state` | `format=summary` 获取紧凑局面 |
| `perform_action` | `action` + 可选 `parameters` |
| `search_wiki` | 模糊查卡牌 / 遗物 |
| `get_action_log` | 观战 / 学习玩家操作 |

## 第一层启发式

- 低血量：地图避开精英。
- 战斗：在致死伤害前优先格挡。
- 奖励：全部领取后再 `proceed`。
- 同一回合：能量未用完可多次 `perform_action`，最后 `end_turn`。

## 常见错误

- 复用过期的手牌 `index`。
- 还有能量却只操作一次就结束回合。
