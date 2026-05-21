#!/usr/bin/env python3
"""构建 sts2skill.exe：打包 payload.zip 并嵌入 GUI 安装程序。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUB_DIR = ROOT / "scripts" / "install_stub"
OUT_EXE = ROOT / "sts2skill.exe"
LEGACY_EXE = ROOT / "install.exe"
PAYLOAD_ZIP = ROOT / "dist" / "installer" / "payload.zip"
PUBLISH_DIR = ROOT / "dist" / "installer" / "publish"
PACK_SCRIPT = ROOT / "scripts" / "pack_install_payload.py"


def main() -> int:
    if shutil.which("dotnet") is None:
        print("dotnet not found; install .NET 8 SDK", file=sys.stderr)
        return 1

    print("[1/2] pack payload.zip ...")
    rc = subprocess.call([sys.executable, str(PACK_SCRIPT)], cwd=str(ROOT))
    if rc != 0:
        return rc
    if not PAYLOAD_ZIP.is_file():
        print(f"missing {PAYLOAD_ZIP}", file=sys.stderr)
        return 2

    if PUBLISH_DIR.exists():
        shutil.rmtree(PUBLISH_DIR)
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)

    print("[2/2] dotnet publish (GUI sts2skill.exe) …")
    cmd = [
        "dotnet",
        "publish",
        str(STUB_DIR / "InstallLauncher.csproj"),
        "-c",
        "Release",
        "-o",
        str(PUBLISH_DIR),
    ]
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        return rc

    built = PUBLISH_DIR / "sts2skill.exe"
    if not built.is_file():
        print(f"missing {built}", file=sys.stderr)
        return 3

    for old in (OUT_EXE, LEGACY_EXE):
        if old.is_file():
            old.unlink()
    shutil.copy2(built, OUT_EXE)
    zip_mb = PAYLOAD_ZIP.stat().st_size / (1024 * 1024)
    exe_mb = OUT_EXE.stat().st_size / (1024 * 1024)
    print(f"OK: {OUT_EXE} ({exe_mb:.2f} MB, payload {zip_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
