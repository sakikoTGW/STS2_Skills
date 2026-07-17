# Critical Bug Inspection Playbook

本仓库由定时自动化（cron）扫描近期提交，只处理 **P0 级正确性缺陷**。

## 严重度门槛（必须满足才开 PR）

| 类别 | 示例 |
|------|------|
| 数据丢失/损坏 | 静默截断写入、覆盖用户配置 |
| 崩溃 | 关键路径空指针、未捕获异常导致进程退出 |
| 安全 | 权限绕过、路径穿越写入 |
| 显著用户面破坏 | 工具误报成功、双驱动并发、安装后无法启动 |

**不处理**：风格、文档笔误、纯 UX 降级、无具体触发路径的理论风险。

## 每次巡检流程

1. `git log main -15` — 聚焦最近 5–10 个行为性提交。
2. 对 installer / `sts2_act` / 锁 / MCP 桥接等路径 **追踪完整调用链**，不要只看 diff 关键词。
3. 先查 `main` 是否已有历史修复（如 `_action_http_ok`、`foreign_holder_pid`），避免与未合并的 `cursor/critical-bug-inspection-*` 重复劳动。
4. 发现 P0 → 最小修复 + 针对性测试 → `python3 -m pytest tests/ -q`。
5. 高置信度才 `open_git_pr`；否则仅在自动化输出中记录「未发现 P0」。

## 已知模式（维护者备忘）

### sts2_act 误报成功
- **触发**：STS2MCP 返回 HTTP 200 且 body `{"status":"error",...}`，`handle_sts2_act` 仍 `success=True`。
- **影响**：Agent 以为动作已执行，游戏状态不变，整局卡死或错招。
- **修复**：`_action_http_ok()`；`handle_sts2_act` 与 `_http_result` 统一使用。

### 跨进程 autoplay 锁被抢
- **触发**：进程 A 代打持有 `.autoplay.lock`；进程 B 调 `release_all_driver_locks()` 无条件 `unlink`。
- **影响**：双驱动并发操作游戏；或 B 的 `sts2_act` 在 A 代打时仍被允许。
- **修复**：`foreign_holder_pid()` + `clear_if_stale()`；`manual_act_blocked()` 检测外进程锁。

### Installer 探针跳过部署（非 P0，但需知）
- `install_probe` / `EnvironmentProbe` 在标记齐全时跳过部署，**不校验版本**；升级需强制重装。

### CheckPip 假阳性（非 P0）
- C# `CheckPip` 在未配置 Python 时返回 `PipReady=true`（`ProbePipSkip`），UI 可能显示「全部就绪」但 pip 未装。

## 测试命令

```bash
python3 -m pytest tests/ -q
python3 -m pytest tests/plugins/test_sts2_plugin.py tests/plugins/test_sts2_process_lock.py -q
```

## 未来建议

1. **合并巡检分支**：及时合并 `cursor/critical-bug-inspection-*`，减少重复修复与漏合并。
2. **版本感知安装探针**：在 `probe_install` 中比对 `plugins/sts2/version.py` 与已安装树。
3. **统一 HTTP 成功语义**：`autoplay._execute_action` 已检查 `status==ok`；保持与 `_action_http_ok` 一致。
4. **Installer CheckPip**：Python 未设置时应为 `pip_ready=false`，而非 skip-as-ready。
5. **CI 门禁**：对 `handle_sts2_act` / `release_all_driver_locks` 的回归测试保持在默认 `pytest` 套件中。
