#!/usr/bin/env python3
"""打包 sts2skill.exe 内嵌的 payload.zip（STS2_Skills 源码 + STS2MCP 模组文件）。"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ZIP = ROOT / "dist" / "installer" / "payload.zip"
MOD_API = "https://api.github.com/repos/Gennadiyev/STS2MCP/releases/latest"

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "patches",
    "__pycache__",
    ".pytest_cache",
    "hermes_sts2.egg-info",
    "install_stub",  # dotnet build（bin/obj），勿打进 payload
    "bin",
    "obj",
}
# 安装包不需要测试与未发布说明
SKIP_TOP = {"tests", "patches"}
SKIP_FILES = {"install.exe", "sts2skill.exe", "payload.zip"}
SKIP_SUFFIX = {".pyc"}


def _skip(rel: Path) -> bool:
    if rel.parts and rel.parts[0] in SKIP_TOP:
        return True
    if any(part in SKIP_DIRS for part in rel.parts):
        return True
    if rel.name in SKIP_FILES:
        return True
    return rel.suffix in SKIP_SUFFIX


def _download_mod_assets(dest_mods: Path) -> None:
    dest_mods.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(MOD_API, headers={"User-Agent": "STS2_Skills-installer"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        release = json.loads(resp.read().decode("utf-8"))
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    tag = release.get("tag_name", "?")
    for name in ("STS2_MCP.dll", "STS2_MCP.json"):
        url = assets.get(name)
        if not url:
            raise RuntimeError(f"STS2MCP release {tag} missing asset {name}")
        print(f"[mod] {name} ({tag})")
        dest = dest_mods / name
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "STS2_Skills-installer"}),
            timeout=120,
        ) as r:
            dest.write_bytes(r.read())


def main() -> int:
    OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    staging_mods = OUT_ZIP.parent / "_mods_cache"
    if staging_mods.exists():
        shutil.rmtree(staging_mods)
    staging_mods.mkdir(parents=True)
    try:
        _download_mod_assets(staging_mods)
    except Exception as e:
        print(f"警告：无法下载 STS2MCP 模组（可稍后手动安装）: {e}", file=sys.stderr)

    if OUT_ZIP.is_file():
        OUT_ZIP.unlink()
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in ROOT.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(ROOT)
            if _skip(rel):
                continue
            zf.write(p, arcname=str(Path("STS2_Skills") / rel).replace("\\", "/"))
        for name in ("STS2_MCP.dll", "STS2_MCP.json"):
            f = staging_mods / name
            if f.is_file():
                zf.write(f, arcname=f"STS2_Skills/payload/mods/{name}")
    shutil.rmtree(staging_mods, ignore_errors=True)
    mb = OUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"OK: {OUT_ZIP} ({mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
