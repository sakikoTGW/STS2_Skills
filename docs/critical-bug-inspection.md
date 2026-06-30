# 严重正确性巡检（Critical Bug Inspection）

每日 cron 自动化与人工 review 共用本清单。只处理 **P0**：数据丢失、崩溃、权限绕过、双驱动冲突、静默截断/误报成功。

## 扫描范围

1. 最近 `main` 上 **5–10 个 commit**，优先行为变更（installer、autoplay、sts2_act、锁、存储）。
2. 沿 **完整调用链** 追踪，不只看 diff 关键词。
3. 每个候选 bug 必须能写出 **可复现触发场景**；否则不开 PR。

## 高优先级模式（历史踩坑）

| 模式 | 典型症状 | 检查点 |
|------|----------|--------|
| HTTP 200 假成功 | Agent 以为出牌成功，状态未变 | `handle_sts2_act` / `_http_result` 是否识别 `status:error` |
| 跨进程锁被误删 | 两个进程同时驱动游戏 | `release_all_driver_locks` 是否 `unlink` 活锁；`manual_act_blocked` 是否查 `foreign_holder_pid` |
| 双驱动 | autoplay + 手操交替 | `driver_lock` + `.autoplay.lock` |
| 安装探针假就绪 | 升级后仍显示已就绪、不部署 | `install_probe` / `EnvironmentProbe` 无版本比对 |
| Pip 探针跳过 | 未配置 Python 时 `PipReady=true` | `CheckPip` / `ProbePipSkip` |

## 验证命令

```bash
pip install -e ".[dev]"
python3 -m pytest tests/ -q
```

新增修复须附带 **回归测试**（见 `tests/plugins/test_sts2_plugin.py`、`test_sts2_process_lock.py`）。

## 置信度与输出

- **高置信 P0**：最小修复 + 测试 → 提交并开 PR。
- **不确定或非 P0**：在自动化摘要中记录，**不开 PR**。
- **无 P0**：输出「未发现严重 bug」——这是常态。

## 非 P0（记录但不阻塞发布）

- 安装器：环境已就绪时跳过全量部署，**不比较版本号**；大版本升级需用户勾选强制重装。
- C# `CheckPip`：未找到 Python 时返回 `ProbePipSkip`（视为 pip 就绪），UI 可能显示全绿。

## 未来建议

1. **合并后回归**：将 `cursor/critical-bug-inspection-*` 分支上的修复及时合入 `main`，避免同一 bug 反复巡检。
2. **安装探针加版本**：在 `install_probe` 中比对 `pyproject.toml` / `plugin.yaml` 版本与 payload 版本，避免静默停留在旧 skills。
3. **autoplay 动作结果**：`autoplay.py` 内 `post_singleplayer_action` 也应统一走 `_action_http_ok` 语义。
4. **CI 门禁**：在 `ci.yml` 中保证 `pytest tests/plugins/test_sts2_plugin.py tests/plugins/test_sts2_process_lock.py` 必过。
5. **自动化记忆**：每次巡检结论写入 MCP `automation_memory`（`MEMORIES.md` 索引 + 专题文件）。
