#!/usr/bin/env python3
"""STS2_Skills 一键安装向导：配置宿主、Skill 目录、游戏模组与角色编号。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
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


def _detect_game_dir() -> str:
    os.environ.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))
    try:
        from plugins.sts2.paths import find_game_dir

        found = find_game_dir()
        if found:
            return str(found)
    except Exception:
        pass
    return ""


def _detect_astrbot_data() -> str:
    for cand in (
        Path.home() / ".astrbot" / "data",
        Path(os.environ.get("ASTRBOT_DATA", "")).expanduser(),
    ):
        if cand.is_dir():
            return str(cand)
    return str(Path.home() / ".astrbot" / "data")


def _write_sts2_config(
    *,
    sts2_home: Path,
    character_index: int,
    base_url: str = "http://127.0.0.1:15526",
) -> Path:
    import yaml

    sts2_home.mkdir(parents=True, exist_ok=True)
    cfg_path = sts2_home / "config.yaml"
    section = {
        "base_url": base_url,
        "timeout": 15,
        "character": character_index,
        "commentary": "verbose",
        "autoplay": False,
        "pause_on_ask": False,
        "ask_user_on": [],
        "autopilot_until_victory": True,
        "study_marathon": True,
        "loop_runs": True,
    }
    cfg_path.write_text(
        yaml.safe_dump({"sts2": section}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    os.environ["STS2_CONFIG_PATH"] = str(cfg_path)
    os.environ["STS2_HOME"] = str(sts2_home)
    return cfg_path


def _pip_install(python: str) -> int:
    print(f"\n[pip] {python} -m pip install -e {ROOT}[mcp]")
    return subprocess.call(
        [python, "-m", "pip", "install", "-e", f"{ROOT}[mcp]"],
        cwd=str(ROOT),
    )


def _install_mod(python: str, game_dir: str) -> int:
    env = {**os.environ, "STS2_GAME_DIR": game_dir}
    script = ROOT / "scripts" / "install_sts2_mcp_mod.py"
    print(f"\n[mod] 安装 STS2MCP → {game_dir}/mods/")
    return subprocess.call([python, str(script)], env=env, cwd=str(ROOT))


def _copy_skill(skill_dst: Path) -> None:
    src = ROOT / "skills" / "slay-the-spire-2"
    if not src.is_dir():
        src = (
            ROOT
            / "plugins"
            / "sts2"
            / "integrations"
            / "astrbot"
            / "skills"
            / "slay-the-spire-2"
        )
    if not src.is_dir():
        print(f"[skill] 跳过：未找到 {src}")
        return
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    if skill_dst.exists():
        shutil.rmtree(skill_dst)
    shutil.copytree(src, skill_dst)
    print(f"[skill] 已复制 → {skill_dst}")


def _setup_hermes(sts2_home: Path, character_index: int) -> None:
    import yaml

    hermes_cfg = Path.home() / ".hermes" / "config.yaml"
    hermes_cfg.parent.mkdir(parents=True, exist_ok=True)
    raw = {}
    if hermes_cfg.is_file():
        raw = yaml.safe_load(hermes_cfg.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raw = {}
    sts2 = raw.setdefault("sts2", {})
    if not isinstance(sts2, dict):
        sts2 = {}
        raw["sts2"] = sts2
    sts2.update(
        {
            "base_url": "http://127.0.0.1:15526",
            "character": character_index,
            "pause_on_ask": False,
            "ask_user_on": [],
        }
    )
    hermes_cfg.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"[hermes] 已写入 {hermes_cfg}")
    skill_dst = Path.home() / ".hermes" / "skills" / "slay-the-spire-2"
    _copy_skill(skill_dst)


def _setup_openclaw(
    sts2_home: Path,
    skill_dir: str,
    python: str,
    character_index: int,
) -> None:
    from plugins.sts2.integrations.mcp_config import openclaw_mcp_block

    block = openclaw_mcp_block(
        repo_root=ROOT,
        python=python,
        sts2_home=str(sts2_home),
    )
    block["env"]["STS2_CHARACTER"] = str(character_index)
    oc_home = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
    mcp_path = oc_home / "mcp.sts2.json"
    mcp_path.write_text(json.dumps(block, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[openclaw] MCP 配置片段 → {mcp_path}")
    print("  请合并到 OpenClaw 的 mcp.servers.sts2，或执行文档中的 openclaw mcp set 命令。")
    if skill_dir:
        _copy_skill(Path(skill_dir) / "slay-the-spire-2")


def _setup_astrbot(
    astrbot_data: Path,
    skill_dir: str,
    python: str,
    character_index: int,
    sts2_home: Path,
) -> None:
    from plugins.sts2.integrations.mcp_config import astrbot_mcp_block

    block = astrbot_mcp_block(
        repo_root=ROOT,
        python=python,
        sts2_home=str(sts2_home),
    )
    block["env"]["STS2_CHARACTER"] = str(character_index)
    block["env"]["STS2_CONFIG_PATH"] = str(sts2_home / "config.yaml")
    mcp_json = astrbot_data / "mcp_server.json"
    data: dict = {}
    if mcp_json.is_file():
        try:
            data = json.loads(mcp_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data.setdefault("mcpServers", {})["sts2"] = block
    mcp_json.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[astrbot] MCP 已写入 {mcp_json}")
    if skill_dir:
        dst = Path(skill_dir) / "slay-the-spire-2"
        _copy_skill(dst)
    plugin_cfg = astrbot_data / "config" / "astrbot_plugin_sts2_agent_config.json"
    if plugin_cfg.parent.is_dir():
        plug = {}
        if plugin_cfg.is_file():
            try:
                plug = json.loads(plugin_cfg.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                plug = {}
        plug.update(
            {
                "skills_root": str(ROOT),
                "base_url": "http://127.0.0.1:15526",
                "character": character_index,
                "mcp_python": python,
            }
        )
        plugin_cfg.write_text(
            json.dumps(plug, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[astrbot] 插件配置已更新 {plugin_cfg}")


def run_wizard(args: argparse.Namespace) -> int:
    python = args.python or sys.executable
    host = args.host
    if not host:
        host = _prompt_choice("选择宿主环境", HOSTS)

    game_dir = args.game_dir or _detect_game_dir()
    if not game_dir:
        game_dir = _prompt("杀戮尖塔2 安装目录（含 SlayTheSpire2.exe）")
    if not Path(game_dir).is_dir():
        print(f"错误：游戏目录不存在: {game_dir}", file=sys.stderr)
        return 1

    char_raw = args.character if args.character is not None else _prompt(
        f"开局角色编号 ({CHAR_HELP})", "0"
    )
    from plugins.sts2.character_choice import resolve_character_setting

    char_index, char_canon = resolve_character_setting(char_raw)
    print(f"角色: {char_index} → {char_canon}")

    skill_dir = args.skill_dir
    if host in ("openclaw", "astrbot", "hermes") and not skill_dir:
        default_skill = {
            "astrbot": str(_detect_astrbot_data() / "plugins" / "astrbot_plugin_sts2_agent" / "skills"),
            "openclaw": str(Path.home() / ".openclaw" / "workspace" / "skills"),
            "hermes": str(Path.home() / ".hermes" / "skills"),
        }.get(host, "")
        skill_dir = _prompt("Skill / 插件 skills 目录", default_skill)

    if args.sts2_home:
        sts2_home = Path(args.sts2_home).expanduser()
    elif host == "astrbot":
        sts2_home = Path(_detect_astrbot_data()) / "sts2"
    elif host == "openclaw":
        oc = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
        sts2_home = oc / "sts2"
    else:
        sts2_home = Path.home() / ".config" / "sts2"

    cfg_path = _write_sts2_config(sts2_home=sts2_home, character_index=char_index)
    print(f"[config] {cfg_path}")

    if not args.skip_pip:
        if _pip_install(python) != 0:
            print("警告：pip 安装失败，请手动执行 pip install -e .[mcp]", file=sys.stderr)

    if not args.skip_mod:
        if _install_mod(python, game_dir) != 0:
            print("警告：模组安装失败", file=sys.stderr)

    if host == "hermes":
        _setup_hermes(sts2_home, char_index)
    elif host == "openclaw":
        _setup_openclaw(sts2_home, skill_dir or "", python, char_index)
    elif host == "astrbot":
        ab_data = Path(args.astrbot_data).expanduser() if args.astrbot_data else Path(
            _detect_astrbot_data()
        )
        os.environ["ASTRBOT_DATA"] = str(ab_data)
        _setup_astrbot(ab_data, skill_dir or "", python, char_index, sts2_home)
    elif skill_dir:
        _copy_skill(Path(skill_dir) / "slay-the-spire-2")

    print("\n=== 安装完成 ===")
    print("1. 启动游戏 → 设置 → Mods → 启用 STS2 MCP")
    print("2. 运行: sts2 ping")
    if host == "astrbot":
        print("3. AstrBot WebUI 重载 MCP 与插件，聊天可用 /sts2ai ping")
    print(f"4. 当前角色编号: {char_index}（{CHAR_HELP}）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="STS2_Skills 一键安装向导")
    ap.add_argument(
        "--host",
        choices=["standalone", "hermes", "openclaw", "astrbot"],
        help="宿主环境",
    )
    ap.add_argument("--game-dir", help="游戏安装目录")
    ap.add_argument("--skill-dir", help="Skill 或插件 skills 目标目录")
    ap.add_argument("--astrbot-data", help="AstrBot 数据目录（默认 ~/.astrbot/data）")
    ap.add_argument("--sts2-home", help="STS2_HOME 运行时数据目录")
    ap.add_argument("--python", help="用于 pip / MCP 的 Python 路径")
    ap.add_argument("--character", "-c", help=f"角色编号 0-4（{CHAR_HELP}）")
    ap.add_argument("--skip-pip", action="store_true")
    ap.add_argument("--skip-mod", action="store_true")
    ap.add_argument("-y", "--yes", action="store_true", help="非交互（需提供全部参数）")
    args = ap.parse_args()
    if args.yes and not all([args.host, args.game_dir, args.character is not None]):
        ap.error("非交互模式需 --host --game-dir --character")
    return run_wizard(args)


if __name__ == "__main__":
    raise SystemExit(main())
