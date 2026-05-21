# STS2 × OpenClaw

OpenClaw 与其它 MCP 客户端一样，通过 **同一套 stdio MCP 桥接** 使用 STS2。

## 1. 安装桥接依赖

```bash
pip install mcp
# 或: pip install 'hermes-agent[mcp]'
```

克隆或安装本仓库，确保存在 `scripts/sts2_mcp_bridge.py`。

## 2. 注册 MCP 服务器

```bash
cd /path/to/STS2_Skills
sts2 integration-config --platform openclaw
```

执行输出的 `openclaw mcp set sts2 '...'`，或将 JSON 合并进 OpenClaw 配置中的 `mcp.servers.sts2`。

示例结构：

```json
{
  "command": "/path/to/python",
  "args": ["/path/to/STS2_Skills/scripts/sts2_mcp_bridge.py"],
  "env": {
    "STS2_MCP_BASE_URL": "http://127.0.0.1:15526",
    "STS2_HOME": "/home/you/.openclaw/sts2"
  }
}
```

## 3. Skill

将 `skills/slay-the-spire-2/` 复制到 OpenClaw 工作区 skills（如 `~/.openclaw/workspace/skills/`），按实际安装路径调整。

## 4. 角色选择（自动代打 / 新局）

在 `~/.config/sts2/config.yaml` 中设置：

```yaml
sts2:
  character: 1
```

或在 MCP `env` 中加 `"STS2_CHARACTER": "2"`。命令行：`sts2 autoplay study -c 4`。详见根目录 [README](../../../../README.md#角色选择)。

一键安装：从 [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest) 下载 **`sts2skill.exe`**（或 `python scripts/sts2_setup_wizard.py`）→ 选择 **OpenClaw**。

## 5. 对局循环

1. 启动 STS2 并开启 MCP 模组。
2. 确认 `ping_mod`（或带前缀的变体）成功。
3. 每回合：`get_game_state` → 在对话中规划 → `perform_action`（能量未用完可多次，再 `end_turn`）。

OpenClaw **不使用** Hermes 的 `sts2_get_state` 命名，请以 MCP 工具列表为准。

## 6. 从 Hermes 迁移

若曾使用 `hermes claw migrate`，可继续用 `~/.hermes`，或将 `STS2_HOME` 指向 `~/.openclaw/sts2` 作为 OpenClaw 专用数据目录。
