# 高危正确性巡检 Playbook

每日 cron 自动化聚焦 **数据丢失、崩溃、安全漏洞、显著用户可见故障**。低优先级 UX/风格问题不在范围内。

## 巡检流程

1. 查看 `main` 最近 5–10 条 commit 的行为性 diff（非文档/CI 日志类）。
2. 在动手前 grep 以下哨兵是否已存在（已合并则跳过重复修复）：
   - `_action_http_ok`（`plugins/sts2/tools.py`）
   - `foreign_holder_pid` / `clear_if_stale`（`plugins/sts2/process_lock.py`）
   - `_fastmcp_cls`（`plugins/sts2/mcp_server.py`，mcp 2.x 兼容）
3. 对每条可疑变更 **追踪完整调用链**，构造可复现触发场景；无法构造则不开 PR。
4. 修复后运行：`python3 -m pytest tests/ -q`
5. 仅在高置信度时开 PR；否则在自动化输出中记录「未发现高危问题」。

## 已知高危模式（历史）

| 模式 | 影响 | 关键文件 |
|------|------|----------|
| `sts2_act` HTTP 200 + `status:error` 仍返回 `success=True` | Agent 误以为操作成功，游戏状态漂移 | `tools.py` |
| `release_all_driver_locks` / `start_study` 陈旧恢复无条件删 `.autoplay.lock` | 双进程同时驱动游戏，指令冲突 | `process_lock.py`, `manual_mode.py`, `autoplay.py` |
| Dependabot 将 `mcp` 升到 2.x | `ModuleNotFoundError: mcp.server.fastmcp` | `pyproject.toml`, `mcp_server.py` |
| `character_choice` normalize/index 互相调用 | 递归栈溢出 | `character_choice.py` |

## 非 P0 待办（记录但不每日开 PR）

- 安装器 `CheckPip`：未配置 Python 时 `PipReady=true`（跳过 pip）
- `ba8df63` 增量部署：仅比对文件存在，无版本号，升级需 force reinstall
- `install_probe` / `EnvironmentProbe` 可增加 release 版本校验

## Dependabot 注意

- `mcp>=1.0,<2` 必须保持；若放宽到 `<3` 需先落地 FastMCP 兼容 shim。
- GitHub Actions major 升级需核对 workflow 破坏性变更。

## 锁与单驱动路径

- 进程锁：`plugins/sts2/process_lock.py`
- 线程锁：`plugins/sts2/driver_lock.py`
- 手操入口：`handle_sts2_act` → `manual_act_blocked()`
- 自动打：`AutoplayController.start_study` 陈旧锁恢复
