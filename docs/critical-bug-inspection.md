# 严重缺陷巡检（自动化）

每日 cron 触发的深度巡检，只关注 **数据丢失、崩溃、安全漏洞、显著用户面破坏**。

## 扫描范围

1. 查看 `main` 最近 5–10 条 **行为性** 提交（非纯文档/CI 文案）。
2. 对每条变更追溯 **完整调用链**（caller → callee → 持久化/HTTP/锁）。
3. 运行 `python3 -m pytest tests/ -q`。

## 高优先级模式

| 模式 | 典型触发 | 严重度 |
|------|----------|--------|
| `sts2_act` HTTP 200 + `status:error` 仍 `success=true` | 游戏拒绝出牌但 Agent 继续规划 | P0 |
| 跨进程 `.autoplay.lock` 被 `release_all_driver_locks` 误删 | 双 MCP 进程同时驱动游戏 | P0 |
| `manual_act_blocked` 仅查进程内 `_mode` | 另一进程 autopilot 时手操未被拦 | P0 |
| 安装器 `CopyTree` 整目录删除后覆盖 | 用户自定义 skills 目录被清空 | P1 |
| `install_probe` 无版本校验即 skip deploy | 旧版残留被当作已就绪 | P1（非每日 P0） |
| `CheckPip` 无 Python 时返回 ready | UI 全绿但未 pip install | P2 |

## 置信度门槛

- 必须能描述 **具体复现步骤** 才开 PR 修。
- 存疑则只记日志/Slack，不开 PR。
- 修复保持 **最小 diff**，同 PR 不做大范围重构。

## 自动化记忆

见 Cursor Automation `MEMORIES.md`（历次已修模式与 PR 分支）。

## 给维护者的建议

1. **锁与驱动**：任何改动 `driver_lock` / `process_lock` / `manual_mode` 必须加跨进程测试。
2. **HTTP 语义**：凡包装 STS2MCP 响应，统一用 `_action_http_ok()`，勿手写 `success=True`。
3. **安装器**：增量部署前考虑用户数据目录；`force` 与 `probe` 语义要在 UI 写清。
4. **回归测试**：`tests/plugins/test_sts2_plugin.py` 与 `test_sts2_process_lock.py` 为 P0 守门测试。
