---
name: slay-the-spire-2
description: "通过 API 游玩 STS2；第一层安全循环与通关。"
version: 1.0.3
author: Hermes Agent
license: MIT
tags: [gaming, sts2, ironclad, silent, defect, necrobinder, regent]
platforms: [windows, macos, linux]
metadata.hermes.category: gaming
metadata.hermes.config:
  - sts2.base_url
  - sts2.character
---

# 杀戮尖塔 2 Skill

通过 STS2MCP（`hermes sts2 ping` 或 MCP `ping_mod`）读写游戏状态并执行操作。插件提供局面摘要、操作校验与第一层策略护栏。

## 何时使用

- 用户要通关（`FULL_RUN_CLEARED`）或打完第一层
- 游戏已开、单人模式；角色与配置一致或已在局内

## 前置条件

1. 游戏运行且启用 **STS2 MCP** 模组。
2. `sts2_ping` 返回成功。
3. **角色（可选）：** `sts2.character` 设为 **0–4**（0 铁甲战士、1 静默猎手、2 故障机器人、3 亡灵契约师、4 储君），或 `STS2_CHARACTER=1`。也可从 [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest) 运行 **`sts2skill.exe`** 或 `sts2 install-wizard` 一键配置。
4. 启动 `Launch-Hermes-STS2.bat`（**挂载模式**：边聊边打至通关）。
5. **怪物知识库**（首次）：`hermes sts2 sync-wiki --merge-yaml`（灰机 wiki 需浏览器 cookies 时用 `--cookies`；或 `--html-dir` 导入已保存 HTML）。仓库已内置 Act1 种子，无网也能读【怪物Wiki】。

## 如何运行

### 核心循环（必做）

```text
sts2_get_state(summary=true)
→ 阅读 agent_contract、play_brief、combat_fsm、survival_snapshot
→ 在聊天中写思考（意图、净伤害、地图选择）
→ sts2_act 执行一个操作
→ 重复直至 FULL_RUN_CLEARED
```

**挂载模式**：`sts2_get_state(summary=true)` 含状态机与 `combat_think`；`think_required` 时先写思考再 `sts2_act`。不要用 `sts2_autoplay run`。

### 第一层规则

| 情况 | 规则 |
|------|------|
| 地图血量 &lt; 50% | 不进 `elite`；选 `?` / 营火 / 普通怪 |
| 地图层数 ≤12 且血量 &lt; 72% | 避精英 |
| 地图有营火且血量 &lt; 75% | 优先休息回血 |
| 战斗高伤害回合 | 有能量先格挡再攻击 |
| 花园幽灵鳗精英 | 读【怪物Wiki】Skittish：每回合首次受击获得格挡（可叠）；同回合多段攻击 |
| 战斗规划 | 读 **行为循环** 行：`T+1≈X伤` 含力量与循环序号；总伤超血量前先格挡 |
| 奖励界面 | 先 `claim_reward` 全部（金币优先），再 `proceed` |
| 事件 | `choose_event_option` / `advance_dialogue`，勿用 `menu_select` |
| 战斗同回合 | 能量未用完可多次 `sts2_act`，再 `end_turn` |

第一层时 `validate_action` 可能 **改写** 地图 / 奖励 / 休息失误（`act1_guard=objective`；战斗仍由 LLM 除非 `full`）。注意 `action_corrected` / `act1_policy_applied`。

## 工具速查

| 工具 | 作用 |
|------|------|
| `sts2_get_state(summary=true)` | 观测 + play_brief + 状态机 |
| `sts2_act` | 执行操作（第一层可能被策略改写） |
| `sts2_wiki_search` | 查卡 / 敌人（MCP） |
| `hermes sts2 sync-wiki` | 从灰机 wiki 刷新本地怪物库 |
| `sts2_autoplay action=run` | 启动 LLM 自动代打直至胜利 |
| `sts2_autoplay action=pause\|resume\|stop\|hint` | 控制自动代打 |

## 流程

### 新局

`sts2_ping` → `sts2_get_state` → `sts2_act`（`setup_status` 最多一次）。挂载模式不要用终端直接写 HTTP。

若需**自动开新局并选角色**：配置 `sts2.character` 后使用 `sts2_autoplay action=study`（或 CLI `sts2 autoplay study -c <角色>`）；菜单阶段会 `menu_select` 对应角色，勿假定铁甲战士。

### 直至第一层 Boss 死亡

遵守上表；每场战斗后读奖励摘要再 `proceed`。

### 第二～三层

同一循环；`run.act` &gt; 1 后第一层自动纠偏停止，由你负责全程策略。

## 常见错误

- 猜测 `card_index` — 每次 `sts2_act` 后重新 `get_state`。
- 奖励未领就 `proceed`。
- 还有能量却只 `sts2_act` 一次就停。
- 出牌后仍信任旧手牌索引。

## 验证

- 第三层 Boss 后：`HERMES_HOME/sts2/FULL_RUN_CLEARED.txt`
- 第一层：Boss 房清空，`get_state` 可见第二层地图或胜利过渡
