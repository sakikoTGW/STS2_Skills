# 关键缺陷巡检 Playbook

每日 cron 自动化巡检用。只处理 **P0**：数据丢失、崩溃、安全洞、显著用户可见破坏。

## 巡检范围

1. 查看 `main` 最近 5–10 个 commit 的行为性变更（非样式/文档）。
2. 沿调用链追踪：diff 模式匹配不够，要追到下游效应。
3. 优先路径：
   - `plugins/sts2/tools.py` — `handle_sts2_act` 成功判定
   - `plugins/sts2/process_lock.py` / `driver_lock.py` / `manual_mode.py` — 单驱动锁
   - `plugins/sts2/mcp_server.py` — MCP 依赖兼容
   - `scripts/install_stub/` — 安装器探测与跳过逻辑
   - Dependabot 对 `mcp` 等大版本 bump 的 PR

## 已知模式（grep 快检）

| 模式 | 文件 | 含义 |
|------|------|------|
| `_action_http_ok` | `tools.py` | sts2_act 不把 HTTP 200 + status:error 当成功 |
| `foreign_holder_pid` | `process_lock.py` | 跨进程锁不被误删 |
| `_fastmcp_cls` | `mcp_server.py` | mcp 2.x FastMCP 导入兼容 |

若三项均在 `main` 上存在，可跳过重复修复。

## 置信度门槛

- 必须能描述 **可复现触发场景** 才开 PR。
- 修复后跑：`python3 -m pytest tests/ -q`
- 最小 diff，同 PR 不做大范围重构。

## 非 P0  backlog（记录但不自动开 PR）

- **Installer CheckPip**：未找到 Python 时 `PipReady=true`，可能显示「已全部就绪」却未装 pip。
- **Install probe 跳过部署**：仅比对文件标记，无版本号；升级需勾选强制重装。
- **mcp 2.x**：当前 `pyproject.toml` 为 `mcp>=1.0,<2`；若 Dependabot 放宽到 `<3`，须加 FastMCP shim。

## 自动化输出

- 发现 P0 并修复：开 PR，说明 Bug/影响/根因/验证。
- 未发现 P0：简短「今日无关键缺陷」摘要（预期多数日期如此）。
