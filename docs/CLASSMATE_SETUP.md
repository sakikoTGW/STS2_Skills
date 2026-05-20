# 同学安装指南（STS2_Skills）

给没有参与开发、只想**下载就能用**的同学。

## 1. 下载

打开：**https://github.com/sakikoTGW/STS2_Skills/releases**

- 点最新版本（例如 **v1.1.0**）
- 下载 **`STS2_Skills-1.1.0.zip`**（或页面上的 Source zip）

不要只收藏仓库主页——**Releases** 里才有带说明的正式包。

## 2. 环境

| 需要 | 说明 |
|------|------|
| Python | 3.11 或更高 |
| 杀戮尖塔 2 | Steam 正版 |
| STS2MCP 模组 | 见下文 `sts2 install-mod` |

## 3. 安装步骤（Windows 示例）

```powershell
# 解压到 D:\STS2_Skills 后：
cd D:\STS2_Skills
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[mcp]"

mkdir $env:USERPROFILE\.config\sts2 -Force
copy config.example.yaml $env:USERPROFILE\.config\sts2\config.yaml

sts2 install-mod
```

1. 启动游戏 → **单机** → 模组列表里启用 **STS2 MCP**
2. 进一局后执行：`sts2 ping`（应返回成功）

## 4. 接到 AI 里（三选一）

### OpenClaw

```powershell
sts2 integration-config --platform openclaw
```

把输出的 JSON 配到 OpenClaw 的 MCP 里（`openclaw mcp set sts2 '...'`）。

### AstrBot

WebUI → MCP → 添加服务器，粘贴：

```powershell
sts2 integration-config --platform astrbot --json-only
```

### Hermes Agent

把本仓库放到 Hermes 的 `plugins/sts2`，或 `pip install git+https://github.com/sakikoTGW/STS2_Skills.git[mcp]`，然后 `hermes sts2 setup`。

## 5. 常见问题

| 现象 | 处理 |
|------|------|
| `sts2 ping` 连不上 | 游戏是否已开、模组是否启用、防火墙是否拦 127.0.0.1:15526 |
| 没有 `sts2` 命令 | 确认已 `activate` 虚拟环境且 `pip install -e ".[mcp]"` 成功 |
| MCP 工具名带前缀 | 正常，用界面里显示的名字（如 `sts2_get_game_state`） |

## 6. 只看代码、不安装

仓库主页 **Code → Download ZIP** 也可以，但 **Releases** 版本号固定，方便对照作业/报告。
