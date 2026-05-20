# STS2 × AstrBot

[AstrBot MCP](https://docs.astrbot.app/en/use/mcp.html)（v3.5+）可挂载本仓库提供的 STS2 stdio MCP 服务。

## 1. 依赖

- 游戏 + [STS2MCP](https://github.com/Gennadiyev/STS2MCP) 模组
- 在 **与 AstrBot 相同的 Python 环境** 中执行 `pip install mcp`
- 本仓库（或 `pip install hermes-agent` 以使用 `plugins.sts2`）

## 2. WebUI 配置

```bash
sts2 integration-config --platform astrbot --json-only
```

在 AstrBot WebUI → **MCP** → 添加服务器 → 粘贴 JSON：

- **command**：你的 Python 可执行文件路径
- **args**：`["/绝对路径/scripts/sts2_mcp_bridge.py"]`
- **env**：`STS2_MCP_BASE_URL`、`STS2_HOME` 等

AstrBot 数据在 `~/AstrBot/data` 时，示例：

```json
"STS2_HOME": "/home/you/AstrBot/data/sts2"
```

或在 env 中设置 `ASTRBOT_DATA=/home/you/AstrBot/data`。

## 3. Skill（可选）

将 `skills/slay-the-spire-2/` 复制到：

- `AstrBot/data/plugins/<你的插件>/skills/slay-the-spire-2/`，或
- Agent 会读取的工作区 skills 目录。

在 WebUI 中重载插件 / Skill。

## 4. 角色选择

写入 `~/.config/sts2/config.yaml` 或 MCP 的 `env`：

```yaml
sts2:
  character: necrobinder
```

取值：`ironclad`、`silent`、`defect`、`necrobinder`、`regent`。用于 `sts2 autoplay` 驱动菜单 / 新局。详见根目录 [README 角色选择章节](../../../../README.md#角色选择)。

## 5. 工具名称

AstrBot 中 MCP 工具常带服务器前缀。典型循环：

1. `get_game_state`，`format=summary`
2. `perform_action`，传入 `action` 与 `parameters`
3. 需要时 `search_wiki` 查卡牌说明

## 6. 仅用 MCP 即可

一般 **不必** 再写 Star 插件；MCP 是推荐的跨平台方式。若需不经过 MCP 的原生 HTTP 插件，可在自己的 fork 中扩展——当前官方路径以 MCP 为准。
