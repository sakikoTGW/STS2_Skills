# 严重缺陷巡检自动化说明

本仓库由定时自动化（cron）扫描近期提交，只处理 **P0 级正确性缺陷**。

## 巡检范围

- 最近 5–10 个 `main` 提交
- 行为变更、安装器、驱动锁、游戏 API 交互等高影响路径

## 严重级别（必须能构造触发场景）

| 类别 | 示例 |
|------|------|
| 数据丢失 | 静默截断、错误覆盖配置 |
| 崩溃 | 关键路径空指针、未捕获异常 |
| 安全 | 权限绕过 |
| 用户可见破坏 | 双驱动同时操作游戏、API 失败却报 success |

**不报告**：风格、纯文档、理论边缘、仅 UX 降级。

## 已知模式（合并后请从待办删除）

1. **`sts2_act` 假成功**：HTTP 200 + `status: error` 仍 `success=True` → `_action_http_ok()`（`plugins/sts2/tools.py`）
2. **跨进程锁误删**：`release_all_driver_locks` / `start_study` 陈旧恢复无条件 `unlink` → `clear_if_stale()` + `foreign_holder_pid()`（`process_lock.py`）
3. **安装器 Pip 假阳性**（非 P0）：Python 未配置时 `CheckPip` 返回 ready
4. **安装跳过无版本校验**（非 P0）：`all_ready` 时跳过部署，升级需强制重装

## 自动化工作流

1. `git log main -10` 看近期 diff
2. `grep` 确认上述修复是否已在 `main`（避免重复开 PR）
3. 追踪完整调用链，不写「看起来可疑」的补丁
4. 修复后：`python3 -m pytest tests/ -q`
5. 仅在高置信度时开 PR；无疑似 P0 则记录「今日无严重缺陷」

## 分支策略

- 在 `cursor/critical-bug-inspection-*` 开发
- **尽快合并到 `main`**，避免数十个并行巡检分支重复劳动

## 测试锚点

- `tests/plugins/test_sts2_plugin.py::test_act_reports_api_error_as_failure`
- `tests/plugins/test_sts2_process_lock.py`
