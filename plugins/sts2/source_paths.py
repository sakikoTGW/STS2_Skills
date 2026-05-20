"""Write pointer so Hermes does not patch E:\\Hermes\\sts2 by mistake."""

from __future__ import annotations

from pathlib import Path


def plugin_source_dir() -> Path:
    return Path(__file__).resolve().parent


def write_source_pointer() -> None:
    from plugins.sts2.storage import sts2_home

    repo = plugin_source_dir()
    home = sts2_home()
    text = (
        "# STS2 源码在这里（不要改本目录下的 explore_*.py / patch_*.py）\n\n"
        f"**插件源码:** `{repo}`\n\n"
        f"- bundle_select: `{repo / 'bundle_select_brain.py'}`\n"
        f"- 决策总线: `{repo / 'decision.py'}`\n"
        f"- 督导代打: `{repo.parent.parent / 'scripts' / 'sts2_supervisor_until_clear.py'}`\n\n"
        "本文件夹 (`sts2/`) 只存日志、策略、live_feed，不是 Python 源码。\n"
        "Hermes 修 bug 请 read/write 上面插件路径。\n"
    )
    try:
        (home / "SOURCE_CODE_POINTER.md").write_text(text, encoding="utf-8")
    except OSError:
        pass


def repo_root() -> Path:
    return plugin_source_dir().parent.parent
