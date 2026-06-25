# Critical Bug Inspection Playbook

自动化每日巡检用。只处理 **P0**：数据丢失、崩溃、安全洞、双驱动/写丢失、显著用户面破坏。

## 扫描范围

1. 最近 `main` 上 **5–10 个 commit**，优先行为变更（installer、driver lock、MCP act、host setup）。
2. 沿 **调用链** 追到下游，不做单纯 diff 关键词匹配。

## 高优先级模式

| 模式 | 典型位置 | 触发场景 |
|------|----------|----------|
| 跨进程锁误删 | `manual_mode.release_all_driver_locks`, `autoplay.start_study` | 进程 A 代打中，进程 B `sts2_act` 或 `start_study` 无条件 `unlink(.autoplay.lock)` |
| `sts2_act` 假成功 | `tools.handle_sts2_act` | STS2MCP HTTP 200 + `{"status":"error"}`，Agent 以为动作成功 |
| PipReady 假阳性 | `EnvironmentProbe.CheckPip` | Python 未配置却 `PipReady=true`，UI 显示全绿 |
| 安装探针跳过升级 | `install_probe` / `Deployer` | 仅检查 marker 文件，不比对版本，升级后仍 skip deploy |
| 角色递归 | `character_choice` | 中文别名 normalize/index 互相调用 |

## 修复原则

- 最小 diff，同一 PR 不做大重构。
- 修复后跑：`python3 -m pytest tests/ -q`
- **高置信才开 PR**；不确定则只记 Slack/内存，不开 PR。

## 非 P0（记录但不修）

- 安装探针无版本号 → 需用户勾选 force reinstall
- `CheckPip` 在无 Python 时 skip（设计如此，但应在 UI 标明「未检测 pip」）

## 自动化记忆

见仓库 Automation Memory：`MEMORIES.md`（Cursor Automation 持久化目录）。
