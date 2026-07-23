# 严重缺陷巡检指南（Critical Bug Inspection）

供 Cursor Automation 每日 cron 巡检使用。目标：只报告/修复会导致**数据丢失、崩溃、安全漏洞或显著用户面破坏**的问题。

## 巡检范围

1. 查看 `main` 最近 **5–10** 个 commit 的行为变更（`git log main -10`、`git diff main~10..main --stat`）。
2. 优先审查高爆炸半径路径：
   - `plugins/sts2/tools.py`（`handle_sts2_act`、HTTP 成功判定）
   - `plugins/sts2/driver_lock.py`、`process_lock.py`、`manual_mode.py`（单驱动/跨进程锁）
   - `plugins/sts2/autoplay.py`（后台自动打牌）
   - `scripts/install_stub/*`、`plugins/sts2/install_probe.py`（安装器跳过部署）
   - `plugins/sts2/mcp_server.py`（MCP 直连动作）
3. 对每个疑点**追踪完整调用链**，不要只看 diff 关键词。

## 高严重度模式清单

| 模式 | 典型症状 | 关键文件 |
|------|----------|----------|
| 假成功 | HTTP 200 但 `status:error`，工具仍 `success:true` | `tools.py` |
| 双驱动 | 手操与 autoplay 同时向游戏发动作 | `driver_lock.py`, `manual_mode.py` |
| 锁窃取 | `unlink(.autoplay.lock)` 删掉他进程仍持有的锁 | `manual_mode.py`, `autoplay.py` |
| 安装假就绪 | probe 全绿但 pip/版本未更新 | `install_probe.py`, `EnvironmentProbe.cs` |
| 递归/崩溃 | 配置解析无限递归 | `character_choice.py` |

## 置信度门槛

- 必须能描述**具体触发场景**（谁调用、什么状态、什么后果）。
- 无法构造合理触发路径 → **不开 PR**，仅在 memory/Slack 记观察项。
- 修复保持**最小 diff**，避免同 PR 大范围重构。

## 验证命令

```bash
python3 -m pytest tests/ -q
python3 -m ruff check plugins/sts2 tools.py  # 若改动 Python
```

## 已知非 P0（记录但不阻塞发布）

- **Install probe 跳过部署**：`ba8df63` 在 marker 匹配时跳过全量部署，**不校验版本**；升级需强制重装。
- **CheckPip 假阳性**：C# `EnvironmentProbe.CheckPip` 在 Python 未配置时返回 `ProbePipSkip`（视为 ready）。
- **mcp_server.perform_action**：未统一 `_action_http_ok`；MCP 客户端需读 `result.status`。

## 自动化运行流程

1. `git fetch origin main` → 基于 `main` 创建/更新 `cursor/critical-bug-inspection-*` 分支。
2. **先检查 main 是否已有当日修复**（grep `_action_http_ok`、`foreign_holder_pid`）。
3. 发现问题且高置信 → 修复 + 测试 → `git commit` → `git push -u origin <branch>` → `open_git_pr`。
4. 未发现 P0 → 更新 automation memory，**不开 PR**。
5. 将 `cursor/critical-bug-inspection-*` **及时合并进 main**，避免多分支重复劳动。

## 后续改进建议

1. 抽取共享 `action_http_ok()` 供 `tools.py` 与 `mcp_server.py` 共用。
2. `install_probe` / `EnvironmentProbe` 增加 **版本号或 payload 哈希** 比对，避免旧版误跳过升级。
3. `CheckPip`：Python 未配置时应为 `pip_ready=false`，UI 不得显示全绿。
4. `autoplay.py` 中残留的 `.autoplay.lock` 无条件 `unlink` 应改为 `clear_if_stale`。
5. CI 增加针对 `foreign_holder_pid` / `_action_http_ok` 的回归 job，防止修复只存在于 orphan 分支。
