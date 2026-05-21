# STS2_Skills

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**简体中文** · [English](README.en.md)

面向 **杀戮尖塔 2（Slay the Spire 2）** 的 Agent 工具包，通过 [STS2MCP](https://github.com/Gennadiyev/STS2MCP) 与游戏通信。可将局面与操作暴露给 LLM 宿主：Hermes Agent 原生工具，或 stdio [MCP](https://modelcontextprotocol.io/) 服务（OpenClaw、AstrBot、Cursor 等）。

**最新发布：** [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest)

## 功能

- 对接游戏内 STS2MCP HTTP API（`get_state`、`act`、百科检索）
- **可配置开局角色**，自动代打 / 新局菜单不再固定铁甲战士
- 内置知识库（机制、地图流程、遗物、Wiki 爬取快照）
- 可选战斗辅导、第一层策略护栏、观战与操作日志
- 支持 **Hermes Agent**、**OpenClaw**、**AstrBot** 集成

## 环境要求

- Python 3.11+
- 杀戮尖塔 2（Steam）
- 单人模式启用 [STS2MCP](https://github.com/Gennadiyev/STS2MCP) 模组
- 游戏 API 默认 `http://127.0.0.1:15526`（可配置）

## 安装

### 从 Release 压缩包

1. 在 [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest) 下载最新源码 `.zip`（Windows 一键安装可另下 **`sts2skill.exe`**）。
2. 解压后在项目根目录打开终端。

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[mcp]"
```

将 `config.example.yaml` 复制为 `~/.config/sts2/config.yaml`（Windows：`%USERPROFILE%\.config\sts2\config.yaml`）；使用 Hermes 时也可把 `sts2:` 段合并进 `~/.hermes/config.yaml`。

### 从 Git

```bash
git clone https://github.com/sakikoTGW/STS2_Skills.git
cd STS2_Skills
pip install -e ".[mcp]"
```

```bash
pip install "git+https://github.com/sakikoTGW/STS2_Skills.git[mcp]"
```

## 快速开始

### 图形安装（Windows）

在 [Releases](https://github.com/sakikoTGW/STS2_Skills/releases/latest) 下载 **`sts2skill.exe`**，双击运行（图形界面，**中/英** 可切换）。安装程序会：

1. 选择 **宿主**（独立 / Hermes / OpenClaw / AstrBot）
2. 用 **浏览** 按钮选择 **宿主数据目录**、**游戏安装目录**、**STS2_Skills 安装目录**
3. 将内嵌的 STS2_Skills 与 STS2MCP 模组 **解压到对应路径**，并写入 MCP、插件与 `config.yaml`

命令行备选：`python scripts/sts2_setup_wizard.py` 或 `sts2 install-wizard`（需已有 Python 环境）。

**版本号**：采用 `1.0.x` 小版本；从旧 **v1.3.0** / 插件 **v2.x** 迁移见 [VERSION_MIGRATION.md](VERSION_MIGRATION.md)。

### 按宿主一键配置

```bash
sts2 setup --host openclaw --install-mod    # 写入 ~/.openclaw/openclaw.json + sts2 配置
sts2 setup --host astrbot --install-mod     # 同步 AstrBot 插件 + mcp_server.json
sts2 setup --host hermes --install-mod      # 需已安装 Hermes CLI；否则写入 ~/.hermes
sts2 setup --host standalone                # ~/.config/sts2 + MCP 片段
python scripts/sts2_setup_wizard.py         # 交互式同上
```

### 手动步骤

```bash
sts2 install-mod          # 将 STS2MCP 安装到游戏 mods/ 目录
# 启动游戏（单人 + 模组开启）
sts2 ping                 # 检测 API 是否连通
sts2 status               # 查看 base_url、角色编号、autoplay 等
```

### 指定角色自动游玩

```bash
# 单次（命令行，编号或名称均可）
sts2 autoplay study --character 1
sts2 autoplay study -c 静默猎手

# 持久（配置文件 character: 0–4，见下文）
sts2 autoplay start -c 2
```

为第三方宿主生成 MCP 配置：

```bash
sts2 integration-config --platform openclaw
sts2 integration-config --platform astrbot --json-only
```

直接运行 stdio MCP 桥接：

```bash
sts2-mcp
# 或: python scripts/sts2_mcp_bridge.py
```

## 配置

| 变量 / 文件 | 用途 |
|-------------|------|
| `config.example.yaml` → `~/.config/sts2/config.yaml` | `base_url`、`character`、超时、autoplay 开关 |
| `STS2_MCP_BASE_URL` | 覆盖 API 地址（默认 `http://127.0.0.1:15526`） |
| `STS2_CHARACTER` | 当前终端会话覆盖角色（编号 0–4 或名称） |
| `STS2_HOME` | 运行时数据（日志、策略、轨迹） |
| `OPENCLAW_HOME` / `ASTRBOT_DATA` | 各宿主下的 `…/sts2` 默认目录 |

完整默认项见 `plugins/sts2/config.py`。

### 角色选择

自动代打或菜单自动化开**新局**时，按配置选择角色，而不再默认铁甲战士。

| 编号 | 规范 ID | 中文名 |
|------|---------|--------|
| **0** | `IRONCLAD` | 铁甲战士 |
| **1** | `SILENT` | 静默猎手 |
| **2** | `DEFECT` | 故障机器人 |
| **3** | `NECROBINDER` | 亡灵契约师 |
| **4** | `REGENT` | 储君 |

**优先级（高者生效）：** 环境变量 `STS2_CHARACTER` → YAML 中 `sts2.character`（**0–4**）→ 默认 **0**（铁甲战士）。

**1. 配置文件** — 复制 `config.example.yaml` 后设置：

```yaml
sts2:
  character: 1   # 0–4，见上表
```

Windows：`%USERPROFILE%\.config\sts2\config.yaml`  
Hermes 用户可在 `~/.hermes/config.yaml` 的 `sts2:` 下写入相同字段。

**2. 环境变量**

```bash
# bash
export STS2_CHARACTER=3

# PowerShell
$env:STS2_CHARACTER = "4"
```

**3. 命令行**（仅对该次命令设置 `STS2_CHARACTER`）

```bash
sts2 autoplay start --character 2
sts2 autoplay study -c 1
sts2 autoplay run --character 4 --max-steps 500
```

用 `sts2 status` 确认（例如 `character: 1 (SILENT)`）。

> **说明：** 组牌与战斗启发式在 **铁甲战士**（编号 0，`ironclad_builds.py`）上最完整；其它角色使用通用规则与 Wiki，能玩但可能弱于专精指南。

## 宿主集成

### Hermes Agent

```bash
hermes sts2 setup
hermes sts2 install-mod
hermes sts2 ping
```

内置 Skill：`skills/slay-the-spire-2/`。完整 Hermes 仓库中本树位于 `plugins/sts2/`。

### OpenClaw

```bash
sts2 integration-config --platform openclaw
```

将输出的 JSON 注册到 `openclaw mcp set sts2 '…'` 或 `mcp.servers.sts2`。Skill 模板：`plugins/sts2/integrations/openclaw/skills/slay-the-spire-2/`。详见 [OpenClaw 集成说明](plugins/sts2/integrations/openclaw/README.md)。

### AstrBot

需要 AstrBot ≥ 3.5 且启用 MCP（[文档](https://docs.astrbot.app/en/use/mcp.html)）。执行：

```bash
sts2 integration-config --platform astrbot --json-only
```

将 JSON 粘贴到 WebUI 的 MCP 设置。详见 [AstrBot 集成说明](plugins/sts2/integrations/astrbot/README.md)。

## MCP 工具

| 工具 | 说明 |
|------|------|
| `ping_mod` | API 健康检查 |
| `get_game_state` | 局面快照（建议 `format=summary`） |
| `perform_action` | 执行一个游戏操作 |
| `search_wiki` | 卡牌 / 遗物检索 |
| `observe_player_actions` | 轮询玩家手动操作 |
| `get_action_log` | 近期推断操作记录 |

各宿主可能对工具名加前缀（如 `sts2_get_game_state`），以 MCP 客户端列表为准。

## 目录结构

```
plugins/sts2/          # 核心插件、知识库、宿主集成文档
scripts/               # MCP 桥接、模组安装脚本
skills/                # Agent Skill（slay-the-spire-2）
tests/                 # pytest 测试
config.example.yaml    # 配置示例
```

运行时数据写在 `STS2_HOME`，不随仓库分发。

## 开发

```bash
pip install -e ".[mcp,dev]"
pytest
ruff check plugins scripts tests
```

见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 知识库维护

```bash
sts2 sync-wiki --merge-yaml
sts2 crawl-wiki --integrate
```

`plugins/sts2/references/` 下 JSON 来自公开 Wiki；请遵守 [wiki.gg](https://slaythespire.wiki.gg) 及第三方站点条款。勿提交 cookies 或 API 密钥。

## 许可证

MIT — 见 [LICENSE](LICENSE)。游戏资源与 STS2MCP 模组不包含在本仓库中。
