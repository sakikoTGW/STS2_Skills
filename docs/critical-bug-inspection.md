# 关键缺陷巡检指南

本仓库由定时 Automation 扫描 `main` 近期提交，只处理**高严重性**正确性问题。

## 严重性标准（必须满足）

| 类别 | 示例 |
|------|------|
| 数据丢失/损坏 | 锁被误删导致双驱动同时操作游戏 |
| 崩溃 | 关键路径空指针、无限循环 |
| 安全 | 权限绕过 |
| 用户可见严重破坏 | Agent 认为动作成功但游戏未执行 |

**不处理**：风格、低概率边界、无具体触发场景的理论风险。

## 每次巡检流程

1. `git log main -10` — 只看最近 5–10 个提交的行为变更。
2. 对 installer / `sts2_act` / 锁 / 存储 等高爆炸半径路径做**调用链追踪**，不要只看 diff 关键词。
3. 先 `grep` 是否已有修复（避免重复劳动）：
   - `_action_http_ok`
   - `foreign_holder_pid` / `clear_if_stale`
4. 发现缺陷须能写出**具体触发步骤**；否则不开 PR，仅在结论中记录。
5. 修复后：`python3 -m pytest tests/ -q`
6. 最小 diff + 回归测试；禁止同 PR 大范围重构。

## 已知高危模式（历史）

### sts2_act 假成功

- **现象**：HTTP 200 + `{"status":"error"}` 仍返回 `success: true`。
- **影响**：Agent 跳过后续 `get_state`，战斗/选牌逻辑错乱。
- **修复**：`tools._action_http_ok()`；测试 `test_act_reports_api_error_as_failure`。

### 跨进程锁窃取

- **现象**：`release_all_driver_locks` / `start_study` 陈旧恢复无条件 `unlink(.autoplay.lock)`；`manual_act_blocked` 只查进程内 `_mode`。
- **影响**：进程 A 自动打牌时，进程 B 手操可删掉 A 的锁并同时发指令 → 双驱动。
- **修复**：`process_lock.foreign_holder_pid` + `clear_if_stale`；测试 `tests/plugins/test_sts2_process_lock.py`。

### 角色名解析递归（已修于 main）

- `character_choice._canonical_from_text` 勿与 `normalize_character` 交叉调用。

## 非 P0 待办（记录即可）

- 安装器 `install_probe`：环境已就绪时跳过部署，**无版本号** — 升级需强制重装。
- C# `EnvironmentProbe.CheckPip`：Python 未配置时可能误报 pip 就绪。
- `mcp_server.perform_action`：未统一 `_action_http_ok` 语义（MCP 客户端应读 `result.status`）。

## 分支与合并

- 巡检分支：`cursor/critical-bug-inspection-*`
- **尽快合并**已验证的巡检 PR，避免多分支重复修同一 bug。
- 开 PR 前确认 `main` 是否已包含相同修复。

## 输出约定

- **有 P0 修复**：PR 含 Bug/根因/修复/测试说明。
- **无 P0**：简短「未发现关键缺陷」+ 可选非 P0 观察项。
