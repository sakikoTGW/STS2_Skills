# Critical Bug Inspection Playbook

自动化巡检（Cursor Automation）用于在合并前发现 **P0 级正确性缺陷**。仅处理会导致数据丢失、崩溃、安全漏洞或显著用户可见故障的问题。

## 每次运行流程

1. 查看 `main` 最近 5–10 个 commit 与当前 PR diff。
2. 对行为变更 **追踪完整调用链**（caller → callee → 下游副作用），不要只做关键词匹配。
3. 先 `grep main` 是否已有修复：`_action_http_ok`、`foreign_holder_pid`、`_fastmcp_cls`。
4. 修复后运行：`python3 -m pytest tests/ -q`
5. **无具体触发场景 + 无通过测试 → 不开修复 PR**；仅 post review 说明「未发现 P0」。

## 高优先级检查清单

| 区域 | 典型 P0 | 触发场景 |
|------|---------|----------|
| `tools.handle_sts2_act` | HTTP 200 + `status:error` 仍 `success=True` | 非出牌阶段 `end_turn` → Agent 误以为成功并继续规划 |
| `process_lock` / `manual_mode` | 无条件 `unlink` 锁文件 | 进程 A 代打 + 进程 B `sts2_act` → 双驱动同时操作游戏 |
| `mcp_server` | `FastMCP` 导入路径 | Dependabot 放宽到 mcp 2.x → `sts2-mcp` 启动即崩溃 |
| `install_probe` | `pip_ready` 假阳性 | Python 未配置时安装器显示全部就绪（非 P0，记录即可） |
| `install_probe` skip deploy | 无版本校验跳过部署 | 升级后旧代码未覆盖（非 P0，需 force reinstall） |

## 依赖升级注意

- **mcp 1.x → 2.x**：`FastMCP` 更名为 `MCPServer`，`from mcp.server.fastmcp import FastMCP` 已移除。本项目通过 `_fastmcp_cls()` 兼容两层 API。
- 合并 Dependabot MCP PR 前必须确认 `_fastmcp_cls` 测试通过。

## 非 P0 积压（记录，不阻塞发布）

- `mcp_server.perform_action` 与 `handle_sts2_act` 的成功语义已部分统一；长期可抽到 `client.action_accepted()`。
- C# 安装器 `CheckPip` 在 Python 未设置时可能误报 ready。
- `character_choice` 递归问题已在 main 修复（`_canonical_from_text` 单向解析）。

## 分支与合并

- 修复分支命名：`cursor/critical-bug-inspection-*`
- **尽快合并**已验证的巡检分支，避免多分支重复劳动。
- 同一 P0 不要在多个分支重复提交；合并前检查 `main` 是否已含修复。

## 未来建议

1. **CI 矩阵**：在 `mcp>=1.29,<2` 与 `mcp>=2.0,<3` 各跑一轮 `pytest`，锁住兼容层。
2. **集成测试**：对 `sts2-mcp` 做 smoke test（import + 注册 tool），防止 SDK 再破坏性变更。
3. **锁文件监控**：`doctor` 子命令输出当前 `.autoplay.lock` 持有者 PID，便于用户自助排查双驱动。
4. **安装探针**：`check_pip` 应区分「import 成功」与「可选 extra 已装」；skip-deploy 应比对 `version` 或 git SHA。
5. **Dependabot 策略**：major 版本依赖 PR 自动触发本巡检；无兼容代码时不合并单纯放宽上界的 PR。
