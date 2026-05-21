# Contributing

感谢参与 [STS2_Skills](https://github.com/sakikoTGW/STS2_Skills)。请先阅读 [README](README.md) 了解安装与宿主集成。

## 开发环境

```powershell
git clone https://github.com/sakikoTGW/STS2_Skills.git
cd STS2_Skills
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[mcp,dev]"
pytest
ruff check plugins scripts tests
```

已安装 `make` 时也可：

```bash
make test
make lint
```

## 提 PR 前

1. 本地 `pytest` 与 `ruff check` 通过（与 CI 一致）。
2. 若修改了 `pyproject.toml` 中的版本号，运行 `./scripts/sync-version.ps1` 并一并提交同步后的 `plugin.yaml`、`compat.yaml`、AstrBot 元数据等。
3. 在 `CHANGELOG.md` 的 `[Unreleased]` 或对应版本下记录用户可见变更。

## 版本与发布（维护者）

| 事项 | 位置 |
|------|------|
| 版本号 | `pyproject.toml` → `[project].version`（唯一来源） |
| 同步元数据 | `scripts/sync-version.ps1` |
| STS2MCP 版本 | `compat.yaml`（固定 tag，不用 `latest`） |
| CI | `.github/workflows/ci.yml` |
| 发布 | 维护者本地执行 `scripts/release.ps1` + `gh` |

发版流程概要：

```powershell
# 1. 更新 pyproject.toml 版本与 CHANGELOG.md
./scripts/sync-version.ps1
git add -A
git commit -m "chore: release v1.0.x"
git tag v1.0.x
git push origin main
git push origin v1.0.x
./scripts/release.ps1
```

请勿将 GitHub token、代理账号密码等写入仓库；使用 `gh auth login` 或系统凭据管理。

## 与 hermes-agent 同步

若在 [hermes-agent](https://github.com/NousResearch/hermes-agent) 中修改了 `plugins/sts2`，请将变更同步到本仓库后在本仓跑测试与 `sync-version.ps1`。

## 报告 Bug

Issue 请尽量包含：Python 版本、`sts2 status` 输出、`compat.yaml` 中的 STS2MCP tag、是否同时启用多个驱动（MCP + autoplay 等）。
