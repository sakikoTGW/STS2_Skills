# 严重正确性巡检（Critical Bug Inspection）

每日 cron 自动化与人工复查共用此清单。只处理 **数据丢失、崩溃、安全洞、显著用户可见破坏**；样式与低概率理论问题跳过。

## 扫描范围

1. 查看 `main` 最近 **5–10** 个提交的行为性 diff（安装器、锁、sts2_act、autoplay、路径解析）。
2. 沿 **调用链** 追踪，不只看 diff 关键词。
3. 先读 `automation_memory`（MCP），确认同类修复是否已在 `main` 落地，避免重复 PR。

## 高优先级模式

| 模式 | 触发场景 | 关键文件 |
|------|----------|----------|
| sts2_act 假成功 | HTTP 200 + `status:error` 仍 `success:true` | `plugins/sts2/tools.py` |
| 跨进程锁误删 | 手操 `release_all_driver_locks` 删掉他进程 autoplay 锁 → 双驱动 | `manual_mode.py`, `driver_lock.py`, `process_lock.py` |
| 安装探针跳过升级 | `install_probe` 仅看文件存在、无版本号 | `install_probe.py`, `Deployer.cs` |
| PipReady 假阳性 | 未配置 Python 时 C# `CheckPip` 返回 ready | `EnvironmentProbe.cs` |

## 验证命令

```bash
python3 -m pytest tests/ -q
```

修复后至少跑相关插件测试；涉及安装器时再跑 `tests/plugins/test_sts2_install_probe.py`。

## 输出规则

- **高置信 P0**：最小 diff + 测试 → 提交分支 → 开 PR。
- **无 P0**：简短「未发现严重问题」+ 非 P0 观察项。
- **不确定**：不要开 PR，记入 memory / 本文件「待观察」。

## 待观察（非 P0）

- `install_probe` / `EnvironmentProbe`：升级后需用户勾选「强制重新安装」。
- `EnvironmentProbe.CheckPip`：Python 未设置时视为 ready（UI 全绿但 pip 未跑）。
- `mcp_server.perform_action`：未统一 `_action_http_ok`（与 `handle_sts2_act` 同类，影响面较小）。

## 分支与合并

- 巡检分支：`cursor/critical-bug-inspection-*`
- **尽快合并** 已验证的巡检 PR，减少重复劳动。

## 给维护者的建议

1. **单驱动契约**：所有 `post_singleplayer_action` 出口应共用 `_action_http_ok`；锁操作只用 `clear_if_stale` / `foreign_holder_pid`。
2. **安装器**：探针增加 `pyproject.toml` 版本或 payload 哈希比对；`CheckPip` 在 Python 缺失时应 `PipReady=false`。
3. **CI**：保持 `pytest tests/` 全绿；Windows 安装器变更需 `release.yml` 产物构建。
4. **Memory**：每次巡检更新 MCP `automation_memory`，记录已修模式与误报教训。
