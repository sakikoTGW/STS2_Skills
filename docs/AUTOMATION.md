# 自动化巡检指南（Critical Bug Inspection）

本仓库由定时自动化扫描近期提交，只处理 **P0 级正确性缺陷**。

## 每次运行前（30 秒）

```bash
git fetch origin main
git log origin/main --oneline -10
grep -r "action_response_ok\|foreign_holder_pid\|_fastmcp_cls" plugins/sts2/ || true
```

若三个符号 **均已存在于 main**，则跳过 act/lock 相关重复 PR。

## 高优先级检查清单

| 类别 | 入口 | 典型触发 |
|------|------|----------|
| 假成功 | `handle_sts2_act`, `perform_action` | HTTP 200 + `{"status":"error"}` 仍返回 `success: true` |
| 双驱动 | `driver_lock`, `process_lock`, `manual_mode` | 手操 `sts2_act` 与 autopilot 同时向游戏发指令 |
| 锁窃取 | `release_all_driver_locks`, `autoplay.start_study` | 误删其他进程持有的 `.autoplay.lock` |
| 依赖断裂 | `pyproject.toml` Dependabot PR | `mcp>=2` 导致 `ModuleNotFoundError: mcp.server.fastmcp` |

## 验证

```bash
pip install pytest -q
python3 -m pytest tests/ -q
```

修复后应新增或更新针对性测试（见 `tests/plugins/test_sts2_process_lock.py`）。

## 非 P0 积压（记录但不自动开 PR）

- 安装器 `install_probe` 无版本校验，升级后可能误判「已就绪」
- C# `CheckPip` 在 Python 未设置时可能误报 ready
- `test_evolution_gate_promotes_on_improvement` Linux CI 偶发 `duplicate_finalize`
- `test_autoplay_step_mock` mock 缺少 `recent_actions` 参数

## 开 PR 门槛

1. 能写出 **具体复现场景**（谁、在什么状态下、触发什么后果）
2. 修复最小化，同 PR 不做大范围重构
3. 全量测试通过

## 合并后

合并 P0 PR 后，后续自动化运行应 grep 到修复符号并 **不再重复提交相同 diff**。
