# 发布到 GitHub（hermes-sts2 1.1.0）

## 1. 生成本地发布树

在 **hermes-agent** 仓库根目录：

```powershell
cd E:\hermes-agent-main
python scripts\build_sts2_github_release.py --zip --github-user 你的GitHub用户名
```

输出：

- `release/hermes-sts2/` — 可直接 `git init` 的完整仓库
- `release/hermes-sts2-1.1.0.zip` — 压缩包

## 2. 新建 GitHub 仓库

1. GitHub → **New repository** → 名称 `hermes-sts2`（或自选）
2. 不要勾选 “Add README”（发布树里已有）

## 3. 首次推送

```powershell
cd release\hermes-sts2
git init
git add .
git commit -m "Release hermes-sts2 1.1.0"
git branch -M main
git remote add origin https://github.com/sakikoTGW/STS2_Skills.git
git push -u origin main
```

## 4. 可选：GitHub Release

```powershell
gh release create v1.1.0 release\hermes-sts2-1.1.0.zip --title "v1.1.0"
```

## 5. 用户安装方式

```bash
pip install git+https://github.com/sakikoTGW/STS2_Skills.git
sts2 ping
```

## 不要提交的内容

- `~/.hermes/.env`、API keys、`huiji_cookies.txt`
- 本机 `E:\Hermes\` 运行日志
- `.venv/`

`.gitignore` 已包含常见项。

## 与上游 Hermes 同步

改 `plugins/sts2/` 后重新运行 `build_sts2_github_release.py`，在 `release/hermes-sts2` 里 commit 并 push。
