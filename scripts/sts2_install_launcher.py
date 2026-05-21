#!/usr/bin/env python3
"""备用：Python 版启动器。正式 GUI 安装程序为 sts2skill.exe（scripts/install_stub）。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _find_python() -> str | None:
    override = os.environ.get("STS2_INSTALL_PYTHON", "").strip()
    if override:
        return override
    for name in ("python", "python3", "py"):
        found = shutil.which(name)
        if found:
            return found
    return None


def main() -> int:
    root = _repo_root()
    os.chdir(root)
    wizard = root / "scripts" / "sts2_setup_wizard.py"
    if not wizard.is_file():
        print(f"错误：未找到安装脚本 {wizard}", file=sys.stderr)
        input("按 Enter 退出…")
        return 2

    python = _find_python()
    if not python:
        print("未找到 Python 3.11+。请安装 Python 并加入 PATH，或设置环境变量 STS2_INSTALL_PYTHON。", file=sys.stderr)
        input("按 Enter 退出…")
        return 1

    print("STS2_Skills 安装向导")
    print(f"  目录: {root}")
    print(f"  Python: {python}\n")
    rc = subprocess.call([python, str(wizard), *sys.argv[1:]])
    if getattr(sys, "frozen", False):
        input("\n按 Enter 退出…")
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
