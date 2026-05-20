# STS2 自动代打手册（插件 Skill）

通过 `skill_view('sts2:autoplay')` 或内置 `slay-the-spire-2` 加载。

## 工具（原生，优先）

- `sts2_setup_status` — 开局前检查安装与配置
- `sts2_get_state` → `sts2_act` — 每回合循环
- `sts2_wiki_search` — 查卡牌 / 遗物文本
- `sts2_get_profile` / `sts2_get_compendium` —  meta 进度

## MCP（可选）

若启用 `mcp_servers.sts2`：可使用 `mcp_sts2_get_game_state`、`mcp_sts2_perform_action` 等。  
两者并存时优先原生 `sts2_*`（同一 HTTP 后端）。

**OpenClaw / AstrBot：** 使用 stdio MCP（`scripts/sts2_mcp_bridge.py`），工具名为 `get_game_state`、`perform_action` 等。  
见 `plugins/sts2/integrations/` 与 `hermes sts2 integration-config`。

## 解说（verbose）

每次 `sts2_act` 前用 2～4 句说明：局面、意图、计划操作。  
若需人工选择（`ask_user_on`），先提问并等待，未答复前勿操作。

## 自动代打

- `sts2_autoplay`：action=start | stop | step | status | hint
- verbose 配置下每步解说
- 战斗结束 / 游戏结束反思 → hot_notes + strategy.yaml
- 轨迹：`~/.hermes/sts2/trajectories/*.jsonl`

## 手动循环

1. `sts2_get_state`（json）
2. 简短解说
3. 若用户发来消息，先回复；暂停时可配合 `sts2_autoplay` hint
4. 仅用当前 state 中的索引 `sts2_act`
5. 重复直至停止、游戏结束或用户打断
