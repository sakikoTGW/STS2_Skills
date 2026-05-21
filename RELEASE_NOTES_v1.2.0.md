# v1.2.0

## 新功能

- **可配置开局角色**：`sts2.character`、`STS2_CHARACTER`、CLI `sts2 autoplay --character`（`ironclad` / `silent` / `defect` / `necrobinder` / `regent`）
- 新模块 `plugins/sts2/character_choice.py`，菜单 / 新局流程不再固定铁甲战士

## 文档

- 项目 README 与集成文档改为**简体中文**（保留 `README.en.md` 英文简版）
- 更新 AstrBot / OpenClaw 集成说明与 Skill 文案

## 安装

```bash
pip install -e ".[mcp]"
# 或解压本 Release 的 STS2_Skills-v1.2.0.zip 后:
pip install -e ".[mcp]"
```

复制 `config.example.yaml` → `%USERPROFILE%\.config\sts2\config.yaml`，设置 `character:` 即可换角色。

## 要求

- Python 3.11+
- 杀戮尖塔 2 + [STS2MCP](https://github.com/Gennadiyev/STS2MCP) 模组
- API 默认 `http://127.0.0.1:15526`
