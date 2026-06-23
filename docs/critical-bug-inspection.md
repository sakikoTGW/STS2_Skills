# 严重缺陷巡检手册（自动化 / 人工）

## 每次巡检流程

1. 查看 `main` 最近 5–10 条提交，优先行为变更（installer、driver、MCP 工具、host setup）。
2. 沿调用链追踪：入口 → 状态写入 → 下游消费者（Agent / GUI / 另一进程）。
3. 只报 **P0**：数据丢失、双驱动、崩溃、鉴权绕过、静默截断、无限循环。
4. 能构造具体触发场景才开 PR；否则只记「无严重缺陷」或记入非 P0 风险。
5. 修复后跑：`python3 -m pytest tests/ -q`

## 高优先级扫描点

| 区域 | 典型 P0 |
|------|---------|
| `handle_sts2_act` / `autoplay._execute_action` | HTTP 200 但 `status:error` 仍报 success |
| `driver_lock` + `process_lock` | 跨进程 `.autoplay.lock` 被 unlink / `manual_act_blocked` 未查文件锁 |
| `release_all_driver_locks` / `start_study` 陈旧恢复 | 无条件删锁导致双督导 |
| `install_probe` / `EnvironmentProbe` | 假阳性「已就绪」跳过部署（无版本校验、pip 跳过） |
| `character_choice` | `normalize` ↔ `index` 互调递归 |
| `host_setup` / 路径探测 | AstrBot `host_path` 指到 `sts2/` 子目录而非 `data/` |

## 已知非 P0（记录即可）

- 安装探针无版本号：升级需勾选「强制重装」。
- `detect_install_paths.py` 对 AstrBot 的 `host_path` 与 GUI 不一致（CLI 专用）。
- CI/发布脚本编码类修复无运行时影响。

## 给仓库维护者的建议

1. **双驱动防护**：任何删 `.autoplay.lock` 必须经 `clear_if_stale()`；`manual_act_blocked` 必须查 `foreign_holder_pid`。
2. **API 成功语义**：凡 `post_singleplayer_action` 结果给 Agent 的路径，统一用 `_action_http_ok()`（与 `card_pick_force` / `autoplay` 一致）。
3. **安装器探针**：Python 未配置时 `PipReady` 应为 false；探针与 `plugins/sts2/install_probe.py` 保持语义一致。
4. **测试**：`tests/plugins/test_sts2_process_lock.py` 锁相关；`test_act_reports_api_error_as_failure` 防回归。
5. **发布前**：Windows 上跑一轮 `sts2skill.exe` 增量安装 + 强制重装；多进程场景下 autoplay + `sts2_act` 互斥。
