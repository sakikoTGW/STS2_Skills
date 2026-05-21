#!/usr/bin/env python3
"""STS2_Skills 一键安装向导：宿主、Skill、游戏模组与角色（调用 integrations.host_setup）。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOSTS = {
    "1": ("standalone", "独立 / Cursor / 通用 MCP"),
    "2": ("hermes", "Hermes Agent"),
    "3": ("openclaw", "OpenClaw"),
    "4": ("astrbot", "AstrBot"),
}

CHAR_HELP = "0=铁甲战士 1=静默猎手 2=故障机器人 3=亡灵契约师 4=储君"


def _prompt(label: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    val = input(f"{label}{hint}: ").strip()
    return val or default


def _prompt_choice(label: str, options: dict[str, str], default: str = "1") -> str:
    print(label)
    for k, (_, desc) in sorted(options.items(), key=lambda x: int(x[0])):
        print(f"  {k}. {desc}")
    while True:
        val = _prompt("请选择", default)
        if val in options:
            return options[val][0]
        print("无效选项，请重试。")


def run_wizard(args: argparse.Namespace) -> int:
    from plugins.sts2.character_choice import resolve_character_setting
    from plugins.sts2.integrations.host_setup import setup_host
    from plugins.sts2.paths import find_game_dir, resolve_astrbot_data_dir
    from plugins.sts2.platform_home import resolve_openclaw_home

    python = args.python or sys.executable
    host = args.host
    if not host:
        host = _prompt_choice("选择宿主环境", HOSTS)

    game_dir = args.game_dir or ""
    if not game_dir:
        found = find_game_dir()
        game_dir = str(found) if found else _prompt("游戏目录（含 SlayTheSpire2.exe）")
    if not Path(game_dir).is_dir():
        print(f"错误：游戏目录不存在: {game_dir}", file=sys.stderr)
        return 1

    char_raw = args.character if args.character is not None else _prompt(
        f"开局角色 ({CHAR_HELP})", "0"
    )
    char_index, char_canon = resolve_character_setting(char_raw)
    print(f"角色: {char_index} → {char_canon}")

    skill_dir = args.skill_dir
    if host in ("openclaw", "astrbot", "hermes") and not skill_dir:
        default_skill = {
            "astrbot": str(
                resolve_astrbot_data_dir()
                / "plugins"
                / "astrbot_plugin_sts2_agent"
                / "skills"
            ),
            "openclaw": str(resolve_openclaw_home() / "workspace" / "skills"),
            "hermes": str(Path.home() / ".hermes" / "skills"),
        }.get(host, "")
        skill_dir = _prompt("Skill 目录", default_skill)

    result = setup_host(
        host,
        repo_root_path=ROOT,
        python=python,
        character_index=char_index,
        game_dir=game_dir,
        sts2_home=args.sts2_home,
        openclaw_home=args.openclaw_home,
        astrbot_data=args.astrbot_data,
        skill_dir=skill_dir,
        install_mod=not args.skip_mod,
        skip_pip=True,
    )

    if not args.skip_pip:
        print(f"\n[pip] {python} -m pip install -e {ROOT}[mcp]")
        if subprocess.call([python, "-m", "pip", "install", "-e", f"{ROOT}[mcp]"], cwd=str(ROOT)) != 0:
            result.warnings.append("pip 安装失败")

    for line in result.messages:
        print(line)
    for warn in result.warnings:
        print(f"警告: {warn}", file=sys.stderr)

    print("\n=== 完成 ===")
    print("1. 游戏内启用 STS2 MCP 模组")
    print("2. sts2 ping")
    if host == "openclaw":
        print("3. 若已写入 openclaw.json：openclaw gateway restart（或重载 MCP）")
    if host == "astrbot":
        print("3. AstrBot WebUI 重载 MCP 与插件 → /sts2ai ping")
    print(f"角色: {char_index}（{CHAR_HELP}）")
    return 0 if result.ok() else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="STS2_Skills 一键安装向导")
    ap.add_argument("--host", choices=["standalone", "hermes", "openclaw", "astrbot"])
    ap.add_argument("--game-dir")
    ap.add_argument("--skill-dir")
    ap.add_argument("--astrbot-data")
    ap.add_argument("--openclaw-home")
    ap.add_argument("--sts2-home")
    ap.add_argument("--python")
    ap.add_argument("--character", "-c")
    ap.add_argument("--skip-pip", action="store_true")
    ap.add_argument("--skip-mod", action="store_true")
    ap.add_argument("-y", "--yes", action="store_true")
    args = ap.parse_args()
    if args.yes and not all([args.host, args.game_dir, args.character is not None]):
        ap.error("非交互模式需 --host --game-dir --character")
    return run_wizard(args)


if __name__ == "__main__":
    raise SystemExit(main())
