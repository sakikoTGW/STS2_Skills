# 自动化巡检说明（Critical Bug Inspection）

本仓库由定时自动化扫描近期提交，只关注 **P0 级正确性缺陷**。

## 每次运行前

```bash
# 若以下符号均已存在于 main，则跳过对应修复的重复 PR
grep -r 'action_response_ok\|foreign_holder_pid\|clear_if_stale' plugins/sts2/
```

## 高优先级检查项

| 区域 | 风险 | 触发场景 |
|------|------|----------|
| `handle_sts2_act` / `_http_result` | 假成功 | HTTP 200 + `{"status":"error"}` 被当成 success |
| `release_all_driver_locks` / `start_study` 恢复 | 锁窃取 | 进程 A 手操时进程 B 的 autoplay 锁被 unlink |
| `manual_act_blocked` | 双驱动 | 仅查进程内 `_mode`，忽略跨进程 `.autoplay.lock` |
| `mcp` 依赖 | 启动崩溃 | `mcp>=2` 移除 FastMCP → `ModuleNotFoundError` |
| Dependabot PR | API 不兼容 | 合并前跑全量测试 |

## 近期提交关注点

- **installer**（`install_probe.py`、`EnvironmentProbe.cs`）：增量部署跳过逻辑；升级场景需 force reinstall（非 P0，但应记录）。
- **路径探测**（`detect_install_paths.py`）：错误路径可能导致安装到错误目录（中危，需具体触发链）。

## 验证命令

```bash
pip install -e ".[dev]"
python3 -m pytest tests/ -q
```

## 输出规范

- 有 P0：最小修复 + 测试 + PR。
- 无 P0：简短「未发现关键缺陷」摘要。
- 用中文回复维护者；附未来建议。

## 已知非 P0  backlog

- `CheckPip` 在 Python 未设置时可能误报 ready
- `test_evolution_gate_promotes_on_improvement` Linux CI 偶发 `duplicate_finalize`
- `test_autoplay_step_mock` mock 缺少 `recent_actions` 参数
