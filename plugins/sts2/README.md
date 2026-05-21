# STS2 插件（杀戮尖塔 2）

通过 [STS2MCP](https://github.com/Gennadiyev/STS2MCP) 连接 **杀戮尖塔 2** 的 Agent 桥接层。可作为 Hermes 后端插件，也可独立安装为 [STS2_Skills](https://github.com/sakikoTGW/STS2_Skills) 包。

## 支持的宿主

| 平台 | 集成方式 | Skill |
|------|----------|-------|
| Hermes Agent | 原生 `sts2_*` 工具 + 可选 MCP | `skills/gaming/slay-the-spire-2` |
| OpenClaw | stdio MCP（`scripts/sts2_mcp_bridge.py`） | `integrations/openclaw/skills/` |
| AstrBot | WebUI 配置 MCP | `integrations/astrbot/skills/` |

## 环境要求

1. 杀戮尖塔 2（Steam）
2. `mods/` 中安装 STS2MCP（`hermes sts2 install-mod` 或 `sts2 install-mod`）
3. 单人模式开启模组；API 默认 `http://127.0.0.1:15526`（可改）

## 快速开始（Hermes）

```bash
hermes sts2 setup
hermes sts2 install-mod
hermes sts2 ping
```

## 快速开始（MCP 宿主）

```bash
pip install mcp
sts2 integration-config --platform openclaw   # 或 astrbot、generic
sts2-mcp
```

各宿主说明见 `integrations/`。独立安装总览：[STS2_Skills 中文 README](../../../README.md)。

## 角色选择

自动代打与 `run_flow` 菜单流程会读取 `sts2.character`，以及 `STS2_CHARACTER`、CLI `--character`。

| 配置方式 | 示例 |
|----------|------|
| `~/.config/sts2/config.yaml` | `character: 1` |
| 环境变量 | `STS2_CHARACTER=2` |
| 命令行 | `sts2 autoplay study --character 4` |

编号：**0** 铁甲战士 · **1** 静默猎手 · **2** 故障机器人 · **3** 亡灵契约师 · **4** 储君（亦支持英文名 / 中文别名）。实现见 `character_choice.py`。

铁甲战士专用组牌/战斗指南在 `ironclad_builds.py`；其它角色暂用通用评分，后续可补充专精文档。

## MCP 工具

| 工具 | 用途 |
|------|------|
| `ping_mod` | API 健康检查 |
| `get_game_state` | 局面快照（`format=summary`） |
| `perform_action` | 执行一个操作 |
| `search_wiki` | 卡牌 / 遗物搜索 |
| `observe_player_actions` | 观战手动游玩 |
| `get_action_log` | 操作轨迹尾部 |

## 运行时数据（`STS2_HOME`）

| 路径 | 内容 |
|------|------|
| `action_log.md` | 观战日志 |
| `strategy/` | 策略 YAML |
| `trajectories/` | 对局 JSONL |
| `knowledge/` | 同步的 Wiki 数据 |

解析顺序：`sts2.log_dir` → `STS2_HOME` → `OPENCLAW_HOME/sts2` → `ASTRBOT_DATA/sts2` → `HERMES_HOME/sts2`。

## 知识库

内置于 `references/`。刷新：`hermes sts2 sync-wiki` / `crawl-wiki`（独立安装用 `sts2` 子命令）。

Wiki 衍生数据仅供个人自动化；遵守来源站点条款。勿提交 `huiji_cookies.txt` 或密钥。
