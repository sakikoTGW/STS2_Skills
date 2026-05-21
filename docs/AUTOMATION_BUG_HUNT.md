# 自动化深度排错说明

本仓库由定时自动化（cron）扫描近期提交中的**严重正确性缺陷**。目标不是风格或理论风险，而是可复现的崩溃、数据丢失、安全漏洞或明显用户可见故障。

## 每次运行应做

1. `git log -20 --stat`：优先看行为变更大的提交（角色/配置、锁、安装脚本、MCP 桥接）。
2. 对可疑 diff **沿调用链走读**（例如 `load_sts2_config` → `character_choice` → `run_flow` / `pick_character_menu_action`），不要只做关键词匹配。
3. 用 `python3 -m pytest tests/` 验证；新增回归应用具体触发场景（环境变量、中文别名、菜单匹配）。
4. **置信度**：必须能写出「用户如何一步步触发」；不确定则只记录结论，不开 PR。

## 高优先级检查点（本项目）

| 区域 | 典型严重问题 |
|------|----------------|
| `plugins/sts2/character_choice.py` | 解析函数互相调用 → `RecursionError`；中文 `STS2_CHARACTER`、英文 ID、菜单 `option_matches_character` |
| `plugins/sts2/config.py` | 默认值与 env 合并顺序错误，导致错误角色或 autopilot 标志 |
| `plugins/sts2/process_lock.py` / `driver_lock` | 锁误释放或死锁，双进程同时驱动游戏 |
| `plugins/sts2/tools.py` | `sts2_act` 校验与生存门控在 agent/manual 模式下的行为不一致 |
| 安装/发布脚本 | 写错路径、覆盖用户配置、下载不完整 mod |

## 修复原则

- 最小 diff；同一 PR 不做大范围重构。
- 有测试则补一条锁定行为的用例。
- 修复后在本分支 commit + push，并 `OpenGitPr`。

## 预期结果

多数日期应输出 **「未发现严重缺陷」**。只有高置信度真 bug 才开 PR。
