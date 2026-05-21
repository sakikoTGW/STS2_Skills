# Contributing

## 成熟项目里各层做什么

| 层级 | 本仓库做法 | 工具 |
|------|------------|------|
| **版本唯一来源** | `pyproject.toml` → `[project].version` | 改版本只改这一处 |
| **元数据同步** | `scripts/sync-version.ps1` 写入 plugin.yaml / compat.yaml / AstrBot | 发版前跑一次 |
| **质量门禁** | GitHub Actions | pytest + ruff + 版本一致性 |
| **发布** | 维护者本机 + `gh` | `scripts/release.ps1`（不用 Cursor Agent 代推） |
| **兼容性** | `compat.yaml` | STS2MCP 固定 tag，非 `latest` |
| **变更记录** | `CHANGELOG.md` | Keep a Changelog |

业务逻辑留在 Python；**CI、发版、版本同步**用 YAML / PowerShell / `gh`，避免再写一套 Python 发布脚本。

## 开发环境

```powershell
cd E:\STS2_Skills
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[mcp,dev]"
pytest
ruff check plugins scripts tests
```

或使用 Make（若已安装 `make`）：

```bash
make test
make lint
```

## 提 PR 前

1. `pytest` 与 `ruff check` 通过（CI 会再跑一遍）。
2. 若改了 `pyproject.toml` 版本：运行 `./scripts/sync-version.ps1` 并一并提交同步后的文件。
3. 在 `CHANGELOG.md` 的 `[Unreleased]` 或新版本下写用户可见变更。

## 发布（维护者，用你的 GitHub 账号）

```powershell
# 1.  bump pyproject.toml version → 1.0.x
# 2.  更新 CHANGELOG.md
./scripts/sync-version.ps1
git add -A
git commit -m "chore: release v1.0.x"
git tag v1.0.x
git push origin main
git push origin v1.0.x

# 3.  本地打 zip（可选 exe）并创建 Release
./scripts/release.ps1
# 或草稿: ./scripts/release.ps1 -Draft
```

需要代理时（Clash 7890）：

```powershell
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
gh auth login
```

**不要**把 GitHub token 写进仓库；用 `gh auth login` 或系统 git credential。

## 从 hermes-agent 单体仓库同步

本仓库已是独立发布树。若在 [hermes-agent](https://github.com/NousResearch/hermes-agent) 中改了 `plugins/sts2`，请用上游的打包脚本复制到本仓，或手工 cherry-pick，然后在本仓跑测试与 `sync-version.ps1`。

## 报告 Bug

请附上：Python 版本、`sts2 status` 输出、STS2MCP 模组版本（`compat.yaml` 中的 tag）、是否多宿主同时驱动（MCP + autoplay）。
