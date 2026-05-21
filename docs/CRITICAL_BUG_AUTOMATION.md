# 严重正确性巡检（Cron Automation）

本仓库由定时任务扫描近期提交，只处理**可复现、高置信度**的数据损坏、崩溃、安全或明显用户可见故障。

## 每次运行应做

1. `git log -20 --stat` 找出行为变更面大的提交（插件、安装器、锁、配置合并）。
2. 对 diff 中的**新函数/新调用链**做端到端推演，不只看正则。
3. 用最小脚本或 `pytest` 验证可疑路径（能 import 则 import，避免被 `plugins.sts2.__init__` 牵连带崩）。
4. **无高置信度问题**：不要开 PR；在自动化输出中写一句「未发现严重缺陷」即可。
5. **有高置信度问题**：最小 diff 修复 + 锁定测试 + 开 PR。

## 本仓库高风险区域

| 区域 | 典型严重问题 |
|------|----------------|
| `plugins/sts2/character_choice.py` | 角色名解析、菜单匹配；易写成互递归 |
| `plugins/sts2/process_lock.py` | 双进程同时 autoplay、锁陈旧 |
| `plugins/sts2/config.py` | 默认值重复键、env 覆盖顺序 |
| `plugins/sts2/integrations/astrbot/` | 同步 LLM 与 asyncio 死锁、强制选卡循环 |
| `scripts/install_stub/Deployer.cs` | `CopyTree` 先删后拷，路径错误即数据丢失 |

## 置信度门槛

- 必须能写出**具体触发步骤**（配置值、环境变量、用户操作）。
- 理论竞态、纯 UX、风格问题 **不报**。
- 修复优先：拆互递归、边界索引、锁 TOCTOU；避免同 PR 大重构。

## 测试注意

- `tests/plugins/test_sts2_character_choice.py` 对 `character_choice` 宜 **按文件 import**，勿经 `plugins.sts2` 包入口（依赖 `tools.registry`）。
- `sts2_env` fixture 定义在 `tests/plugins/test_sts2_plugin.py`；跨文件复用可迁到 `tests/conftest.py`。

## 后续建议

1. **CI**：对 `tests/plugins/test_sts2_character_choice.py` 与 `test_sts2_plugin.py` 子集在 push 时必跑。
2. **角色解析**：保持 `character_index` / `normalize_character` 共用 `_canonical_from_text`，禁止再次交叉调用。
3. **安装器**：对 `SkillsDir` / `HostPath` 做存在性与非空校验后再 `Directory.Delete`。
4. **AstrBot runner**：`patch_llm` 的 sync 回调若在事件循环线程调用，避免 `run_coroutine_threadsafe(...).result()` 同线程等待。
