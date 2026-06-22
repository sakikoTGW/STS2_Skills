# Critical Bug Inspection（自动化巡检说明）

本仓库由定时自动化扫描近期提交，只处理 **数据丢失、崩溃、安全漏洞、显著用户面破坏** 类问题。

## 每次运行流程

1. 查看 `main` 上最近 5–10 个提交的行为性变更（非文档/CI 日志）。
2. 对安装器、锁、驱动、MCP 动作路径做 **调用链追踪**，不单看 diff 关键词。
3. 必须能构造 **可复现触发场景** 才开 PR；不确定则只记录风险、不开 PR。
4. 修复后运行：`python3 -m pytest tests/ -q`
5. 高置信修复：最小 diff + 回归测试 + 推送分支 + OpenGitPr。

## 高优先级扫描区

| 区域 | 典型严重缺陷 |
|------|----------------|
| `plugins/sts2/process_lock.py` / `driver_lock.py` | 跨进程锁被误删 → 双驱动同时操控游戏 |
| `plugins/sts2/autoplay.py` | `start_study` 恢复逻辑、`stop()` 未 join 线程 |
| `plugins/sts2/tools.py` `handle_sts2_act` | HTTP 200 但 `status!=ok` 仍返回 `success=True` |
| `plugins/sts2/manual_mode.py` | `release_all_driver_locks` 无条件 unlink |
| `scripts/install_stub/*` `install_probe.py` | 探测误判「已就绪」跳过升级/ pip（体验级，通常非 P0） |
| `character_choice.py` | 中文别名与 index 互调导致 RecursionError（已修，回归测 `test_sts2_character_choice`） |

## 已知非 P0（记录即可）

- 安装探测无版本号：旧 payload 仍显示「环境已就绪」，需勾选「强制重装」升级。
- C# `CheckPip` 在未配置 Python 时返回 ready：可能跳过 pip，但属安装器 UX。

## 历史修复索引

- **跨进程锁窃取**（2026-06-22）：`clear_if_stale` / `foreign_holder_pid`；见 `tests/plugins/test_sts2_process_lock.py`。
- **sts2_act 误报成功**：与 `autoplay._execute_action` 对齐，`status=="ok"` 才算成功。
