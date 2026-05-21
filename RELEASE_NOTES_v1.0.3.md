# v1.0.3

## 版本策略

- 主版本固定 **1.0**，功能与修复以 **1.0.x** 补丁号递增（替代此前的 1.3.x / 插件 v2.x）。

## 变更

- AstrBot 插件 WebUI：`_conf_schema.json` 中 `character` 为 **int 0–4**（中文 hint）
- 安装：GUI **`sts2skill.exe`**（中英双语），内嵌 payload，选路径后解压到宿主目录、游戏 `mods/`、STS2_Skills 安装目录
- 版本迁移说明：[VERSION_MIGRATION.md](VERSION_MIGRATION.md)（v1.3.0 → 1.0.x）
- 安装向导 / exe 均会同步 `integrations/astrbot/plugin/`（WebUI schema）

## 下载

| 文件 | 说明 |
|------|------|
| `STS2_Skills-v1.0.3.zip` | 源码（不含 exe） |
| `sts2skill.exe` | Windows GUI 安装程序（中英双语） |

从旧版 **v1.3.0** 升级见 [VERSION_MIGRATION.md](VERSION_MIGRATION.md)。
