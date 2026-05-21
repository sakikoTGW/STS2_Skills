#!/usr/bin/env python3
"""打包 sts2skill.exe 内嵌的 payload.zip（STS2_Skills 源码，含 mods/STS2MCP）。"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLED_MODS = ROOT / "mods" / "STS2MCP"
OUT_ZIP = ROOT / "dist" / "installer" / "payload.zip"

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "patches",
    "__pycache__",
    ".pytest_cache",
    "sts2_skills.egg-info",
    "hermes_sts2.egg-info",
    "install_stub",
    "bin",
    "obj",
}
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


def _bundled_ok() -> bool:
    return (BUNDLED_MODS / "STS2_MCP.dll").is_file() and (BUNDLED_MODS / "STS2_MCP.json").is_file()


def main() -> int:
    if not _bundled_ok():
        print("错误：缺少 mods/STS2MCP/STS2_MCP.dll 或 STS2_MCP.json", file=sys.stderr)
        return 1

    OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
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

    mb = OUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"OK: {OUT_ZIP} ({mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
