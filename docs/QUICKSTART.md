# 三分钟上手

面向第一次使用 [STS2_Skills](https://github.com/sakikoTGW/STS2_Skills) 的流程。详细说明见 [README](../README.md)。

## 1. 安装模组

**Windows（图形界面）：** 下载 [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest) 中的 `sts2skill.exe`，选宿主与路径。

**命令行：**

```bash
pip install -e ".[mcp]"
sts2 install-mod
# 或一条命令：sts2 setup --host standalone --install-mod
```

将 STS2MCP 安装到游戏的 `mods/` 目录。

## 2. 启动游戏

- 杀戮尖塔 2 → **单人**
- 设置 → **Mods** → 启用 **STS2 MCP**

## 3. 检查环境

```bash
sts2 doctor
sts2 ping
```

`doctor` 会检查游戏路径、模组文件、API 端口与 MCP 配置；`ping` 需游戏已运行且模组已开。

## 4. 配置宿主（四选一）

| 宿主 | 命令 |
|------|------|
| 独立 / Cursor | `sts2 setup --host standalone` |
| OpenClaw | `sts2 setup --host openclaw --install-mod` |
| AstrBot | `sts2 setup --host astrbot --install-mod` |
| Hermes | `sts2 setup --host hermes --install-mod`（需 Hermes CLI） |

交互式向导：`python scripts/sts2_setup_wizard.py`

## 5. 开始玩

- **Agent + MCP：** 在客户端里用 `get_game_state` / `perform_action`（工具名可能带前缀）
- **命令行代打：** `sts2 autoplay study -c 1`
- **AstrBot：** `/sts2ai auto` 或 `/sts2ai auto llm`

角色编号 **0–4**：铁甲战士、静默猎手、故障机器人、亡灵契约师、储君。见 README「角色选择」。

## 常见问题

| 现象 | 处理 |
|------|------|
| `ping` 连接失败 | 游戏是否开着？模组是否启用？运行 `sts2 doctor` |
| 找不到游戏目录 | 设置环境变量 `STS2_GAME_DIR` |
| OpenClaw 无 MCP 工具 | `sts2 integration-config --platform openclaw --install` 后重载 |
| AstrBot 无响应 | WebUI 重载 MCP 与插件 → `/sts2ai ping` |
