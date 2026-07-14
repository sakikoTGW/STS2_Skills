# 高危缺陷巡检指南

本仓库由定时 Automation 扫描近期提交，只处理 **P0 级正确性缺陷**（数据丢失、崩溃、权限绕过、双驱动并发、静默截断/误报成功）。

## 每次巡检流程

1. **范围**：`main` 最近 5–10 个提交；优先 installer、锁、MCP 动作路径。
2. **追踪调用链**：不要只看 diff 关键词；从入口（`handle_sts2_act`、`Deployer.DeployAll`、`driver_lock`）追到下游。
3. **置信度门槛**：必须能写出可复现触发场景；不确定则只记录、不开 PR。
4. **验证**：修复后运行 `python3 -m pytest tests/ -q`。
5. **去重**：合并前先查 `origin/cursor/critical-bug-inspection-*` 是否已有同类修复。

## 已知高危模式（回归清单）

| 模式 | 症状 | 关键文件 |
|------|------|----------|
| sts2_act 假成功 | HTTP 200 但 `status:error` 仍 `success:true` | `plugins/sts2/tools.py` → `_action_http_ok` |
| 跨进程锁被误删 | `release_all_driver_locks` 无条件 `unlink` 他人 `.autoplay.lock` | `manual_mode.py`, `process_lock.py` |
| 手操未检测外进程锁 | 仅看进程内 `_mode`，另一终端 autoplay 仍可被手操打断 | `driver_lock.manual_act_blocked` |
| autoplay 与手操双驱动 | 两个进程同时 `post_singleplayer_action` | `driver_lock` + `process_lock` |
| 安装器跳过部署 | `install_probe` 全绿但 skills 版本过旧 | `install_probe.py`, `Deployer.cs`（非 P0，升级场景） |
| Pip 探测假阳性 | 未配置 Python 时 `CheckPip` 返回 ready | `EnvironmentProbe.cs`（非 P0，UI 误导） |

## 对照参考实现

- **动作成功判定**：`autoplay._execute_action` 要求 `status == "ok"`；`handle_sts2_act` 须与之一致。
- **锁清理**：只用 `clear_if_stale()`，禁止对外进程存活锁文件 `unlink`。
- **外进程拦截**：`foreign_holder_pid()` + `manual_act_blocked()`。

## 非 P0（记录但不阻塞发布）

- 安装器增量部署无版本比对 → 升级需「强制重装」。
- `CheckPip` 在 Python 未设置时返回 `PipReady=true`。
- 样式、文档、低概率 UX 降级。

## 给维护者的建议

1. **及时合并** `cursor/critical-bug-inspection-*` PR，避免多轮重复修同一 bug。
2. **统一成功语义**：考虑让 `mcp_server` / AstrBot runner 共用 `_action_http_ok`。
3. **安装器**：在 `check_skills` 增加 `compat.yaml` 或 `pyproject.toml` 版本比对；Python 未配置时 `PipReady` 应为 false。
4. **锁相关改动**必须附带 `tests/plugins/test_sts2_process_lock.py` 与 `test_foreign_autoplay_lock_blocks_manual_act`。
5. **CI**：保持 `pytest` 全绿；installer 变更在 Windows 上跑 exe 构建 workflow。
