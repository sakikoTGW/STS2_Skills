"""``hermes sts2`` — setup, mod install, MCP enablement."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from hermes_constants import display_hermes_home, get_hermes_home

from plugins.sts2.config import load_sts2_config, mcp_server_config
from plugins.sts2.paths import find_game_dir, mods_dir


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subs = subparser.add_subparsers(dest="sts2_command", required=True)

    sp_setup = subs.add_parser(
        "setup",
        help="Configure STS2 for Hermes, OpenClaw, AstrBot, or standalone",
    )
    sp_setup.add_argument(
        "--host",
        choices=("standalone", "hermes", "openclaw", "astrbot"),
        default=None,
        help="Target host (default: auto-detect)",
    )
    sp_setup.add_argument("--character", "-c", default=None, help="Character 0-4")
    sp_setup.add_argument("--game-dir", default=None, help="Game install directory")
    sp_setup.add_argument("--sts2-home", default=None)
    sp_setup.add_argument("--openclaw-home", default=None)
    sp_setup.add_argument("--astrbot-data", default=None)
    sp_setup.add_argument("--skill-dir", default=None)
    sp_setup.add_argument(
        "--install-mod",
        action="store_true",
        help="Run install_sts2_mcp_mod after writing config",
    )
    ic = subs.add_parser(
        "integration-config",
        help="Print MCP JSON for OpenClaw, AstrBot, or generic MCP clients",
    )
    ic.add_argument(
        "--platform",
        choices=("openclaw", "astrbot", "generic", "hermes"),
        default="generic",
        help="Host agent (default: generic JSON only)",
    )
    ic.add_argument(
        "--json-only",
        action="store_true",
        help="Print MCP server object only (no comments)",
    )
    ic.add_argument(
        "--repo-root",
        default=None,
        help="STS2_Skills repo root (default: auto-detect)",
    )
    ic.add_argument("--sts2-home", default=None, help="Override STS2_HOME for MCP env")
    ic.add_argument("--openclaw-home", default=None, help="Override OPENCLAW_HOME")
    ic.add_argument("--astrbot-data", default=None, help="Override ASTRBOT_DATA")
    ic.add_argument(
        "--install",
        action="store_true",
        help="Write MCP into host config (OpenClaw openclaw.json / AstrBot mcp_server.json)",
    )
    subs.add_parser("ping", help="Ping STS2MCP HTTP API (game must be running)")
    subs.add_parser("status", help="Show game path, mod dir, config, connectivity")
    subs.add_parser("mode", help="Show STS2 play mode (一口气代打 vs 聊天手操)")

    ap = subs.add_parser("autoplay", help="Background autoplay control")
    ap_sub = ap.add_subparsers(dest="autoplay_command", required=True)

    def _character_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--character",
            "-c",
            default=None,
            metavar="CHAR",
            help="Character: 0-4 or name (0=铁甲战士 1=静默猎手 2=故障机器人 3=亡灵契约师 4=储君)",
        )

    _character_arg(ap_sub.add_parser("start", help="Start autoplay loop (rules, not LLM)"))
    ap_sub.add_parser("stop", help="Stop autoplay / watch / learn")
    ap_sub.add_parser("status", help="Autoplay status")
    ap_sub.add_parser("watch", help="Spectate your manual play (action log)")
    ap_sub.add_parser("learn", help="Learn your style; ask when confused")
    _character_arg(
        ap_sub.add_parser("study", help="Self-play with rules + cross-run lessons")
    )
    start_p = ap_sub.add_parser("step", help="Run one autoplay step")
    start_p.add_argument("--hint", default="", help="User hint for this step")
    sp = ap_sub.add_parser("run", help="Alias: start")
    sp.add_argument("--max-steps", type=int, default=None)
    _character_arg(sp)

    inst = subs.add_parser(
        "install-mod",
        help="Download STS2MCP release into the game mods/ folder",
    )
    inst.add_argument(
        "--game-dir",
        default=None,
        help="Slay the Spire 2 install directory (default: auto-detect)",
    )

    wiz = subs.add_parser("install-wizard", help="一键安装向导（宿主 / Skill / 模组 / 角色）")
    wiz.add_argument(
        "--host",
        choices=["standalone", "hermes", "openclaw", "astrbot"],
    )
    wiz.add_argument("--game-dir", default=None)
    wiz.add_argument("--skill-dir", default=None)
    wiz.add_argument("--astrbot-data", default=None)
    wiz.add_argument("--character", "-c", default=None)
    wiz.add_argument("-y", "--yes", action="store_true", help="非交互模式")

    sw = subs.add_parser(
        "sync-wiki",
        help="Sync monster KB from sts2.huijiwiki.com (needs cookies if CF blocks)",
    )
    sw.add_argument("--html-dir", default=None, help="Import from saved wiki HTML files")
    sw.add_argument("--cookies", default=None, help="Netscape cookie file path")
    sw.add_argument("--max-pages", type=int, default=200)
    sw.add_argument(
        "--merge-yaml",
        action="store_true",
        help="Also write ~/.hermes/sts2/knowledge/enemies.yaml",
    )
    sw.add_argument("--act", type=int, default=None, help="Only merge act N into yaml")

    sm = subs.add_parser(
        "sync-mechanics",
        help="Verify combat math vs wiki examples; optional wiki snapshot cache",
    )
    sm.add_argument(
        "--wiki",
        action="store_true",
        help="Fetch mechanics pages via sts2 wiki_search into user cache",
    )
    sm.add_argument("--max-pages", type=int, default=20)

    subs.add_parser(
        "sync-game-flow",
        help="Print game_flow_kb summary (ascension/rest/ancients)",
    )

    cw = subs.add_parser(
        "crawl-wiki",
        help="Crawl slaythespire.wiki.gg into ~/.hermes/sts2/knowledge/wiki_crawl/",
    )
    cw.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Manifest category: combat_powers, game_flow, characters, acts (repeatable)",
    )
    cw.add_argument("--max-pages", type=int, default=None)
    cw.add_argument(
        "--bundle",
        action="store_true",
        help="Also write into plugins/sts2/references/wiki_crawl/ (ship with repo)",
    )
    cw.add_argument(
        "--integrate",
        action="store_true",
        help="After crawl, merge into game_flow_kb + mechanics_kb JSON",
    )

    subs.add_parser(
        "integrate-wiki",
        help="Parse crawled wiki into merchant/elites/powers KB (no network)",
    )

    cc = subs.add_parser(
        "crawl-catalogs",
        help="Crawl all Events/Relics list pages → events_catalog + relics_index",
    )
    cc.add_argument("--max-events", type=int, default=None)
    cc.add_argument("--max-relics", type=int, default=None)
    cc.add_argument(
        "--no-crawl",
        action="store_true",
        help="Only use already-crawled wiki_crawl/pages (no network)",
    )


def _clear_kb_caches() -> None:
    try:
        from plugins.sts2.game_flow_kb.store import _bundle, load_catalog

        load_catalog.cache_clear()
        _bundle.cache_clear()
    except Exception:
        pass
    try:
        from plugins.sts2.mechanics_kb.store import _merged_bundle, load_catalog

        load_catalog.cache_clear()
        _merged_bundle.cache_clear()
    except Exception:
        pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _enable_sts2_toolset(cfg: dict) -> None:
    tools = cfg.setdefault("tools", {})
    cli_tools = tools.setdefault("cli", {})
    enabled = cli_tools.get("enabled")
    if enabled is None:
        cli_tools["enabled"] = ["sts2"]
        return
    if isinstance(enabled, list) and "sts2" not in enabled:
        enabled.append("sts2")
    elif isinstance(enabled, str) and "sts2" not in enabled:
        cli_tools["enabled"] = f"{enabled},sts2"


def _enable_mcp(cfg: dict) -> None:
    servers = cfg.setdefault("mcp_servers", {})
    servers["sts2"] = mcp_server_config()


def sts2_command(args: argparse.Namespace) -> int:
    cmd = getattr(args, "sts2_command", None)
    if cmd == "setup":
        return _cmd_setup(args)
    if cmd == "integration-config":
        return _cmd_integration_config(args)
    if cmd == "ping":
        return _cmd_ping()
    if cmd == "status":
        return _cmd_status()
    if cmd == "install-mod":
        return _cmd_install_mod(getattr(args, "game_dir", None))
    if cmd == "install-wizard":
        return _cmd_install_wizard(args)
    if cmd == "sync-wiki":
        return _cmd_sync_wiki(args)
    if cmd == "sync-mechanics":
        return _cmd_sync_mechanics(args)
    if cmd == "sync-game-flow":
        return _cmd_sync_game_flow(args)
    if cmd == "crawl-wiki":
        return _cmd_crawl_wiki(args)
    if cmd == "integrate-wiki":
        return _cmd_integrate_wiki(args)
    if cmd == "crawl-catalogs":
        return _cmd_crawl_catalogs(args)
    if cmd == "mode":
        return _cmd_mode()
    if cmd == "autoplay":
        return _cmd_autoplay(args)
    print(f"Unknown sts2 subcommand: {cmd}", file=sys.stderr)
    return 2


def _cmd_mode() -> int:
    from plugins.sts2.mode_display import format_mode_banner, structured_mode_status

    print(format_mode_banner())
    print(json.dumps(structured_mode_status(), indent=2, ensure_ascii=False))
    return 0


def _cmd_autoplay(args: argparse.Namespace) -> int:
    import os

    from plugins.sts2.autoplay import get_controller

    char = (getattr(args, "character", None) or "").strip()
    if char:
        os.environ["STS2_CHARACTER"] = char

    sub = getattr(args, "autoplay_command", "status")
    ctrl = get_controller()
    if sub in ("start", "run", "study"):
        from plugins.sts2.play_mode import llm_marathon_allowed, marathon_blocked_message

        if not llm_marathon_allowed():
            out = {"success": False, "error": marathon_blocked_message()}
        else:
            out = ctrl.start_study()
    elif sub == "stop":
        out = ctrl.stop()
    elif sub == "watch":
        out = ctrl.start_watch()
    elif sub == "learn":
        out = ctrl.start_learn()
    elif sub == "step":
        out = ctrl.step_once(user_hint=getattr(args, "hint", "") or "")
    else:
        out = ctrl.status()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("success", True) else 1


def _cmd_integration_config(args: argparse.Namespace) -> int:
    from plugins.sts2.integrations.mcp_config import (
        astrbot_mcp_block,
        format_integration_doc,
        generic_mcp_block,
        openclaw_mcp_block,
        repo_root_from_plugin,
    )

    platform = getattr(args, "platform", "generic") or "generic"
    repo = Path(args.repo_root).expanduser() if getattr(args, "repo_root", None) else repo_root_from_plugin()
    kwargs = {"repo_root": repo}
    if getattr(args, "sts2_home", None):
        kwargs["sts2_home"] = args.sts2_home
    if getattr(args, "openclaw_home", None):
        kwargs["openclaw_home"] = args.openclaw_home
    if getattr(args, "astrbot_data", None):
        kwargs["astrbot_data"] = args.astrbot_data
    if getattr(args, "json_only", False):
        from plugins.sts2.integrations.mcp_config import hermes_mcp_block

        if platform == "openclaw":
            block = openclaw_mcp_block(**kwargs)
        elif platform == "astrbot":
            block = astrbot_mcp_block(**kwargs)
        elif platform == "hermes":
            block = hermes_mcp_block(**kwargs)
        else:
            block = generic_mcp_block(**kwargs)
        print(json.dumps(block, indent=2, ensure_ascii=False))
        return 0
    if platform == "hermes":
        print(format_integration_doc("hermes", **kwargs))
        return 0
    if getattr(args, "install", False) and platform in ("openclaw", "astrbot", "hermes", "standalone"):
        from plugins.sts2.integrations.host_setup import setup_host

        host = platform if platform != "generic" else "standalone"
        res = setup_host(host, install_mod=False, skip_pip=True)
        for line in res.messages:
            print(line)
        for warn in res.warnings:
            print(f"警告: {warn}", file=sys.stderr)
        return 0 if res.ok() else 1

    print(format_integration_doc(platform, **kwargs))
    return 0


def _cmd_install_wizard(args: argparse.Namespace) -> int:
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "sts2_setup_wizard.py"
    argv = [sys.executable, str(script)]
    if getattr(args, "host", None):
        argv += ["--host", args.host]
    if getattr(args, "game_dir", None):
        argv += ["--game-dir", args.game_dir]
    if getattr(args, "skill_dir", None):
        argv += ["--skill-dir", args.skill_dir]
    if getattr(args, "astrbot_data", None):
        argv += ["--astrbot-data", args.astrbot_data]
    if getattr(args, "character", None) is not None:
        argv += ["--character", str(args.character)]
    if getattr(args, "yes", False):
        argv.append("-y")
    return subprocess.call(argv)


def _cmd_setup(args: argparse.Namespace) -> int:
    from plugins.sts2.character_choice import resolve_character_setting
    from plugins.sts2.integrations.host_setup import setup_host
    from plugins.sts2.platform_home import detect_runtime_host

    host = getattr(args, "host", None) or detect_runtime_host()
    if host not in ("standalone", "hermes", "openclaw", "astrbot"):
        host = "standalone"

    char_index = 0
    if getattr(args, "character", None) is not None:
        char_index, _ = resolve_character_setting(args.character)

    result = setup_host(
        host,
        character_index=char_index,
        game_dir=getattr(args, "game_dir", None) or "",
        sts2_home=getattr(args, "sts2_home", None),
        openclaw_home=getattr(args, "openclaw_home", None),
        astrbot_data=getattr(args, "astrbot_data", None),
        skill_dir=getattr(args, "skill_dir", None),
        install_mod=bool(getattr(args, "install_mod", False)),
    )
    for line in result.messages:
        print(line)
    for warn in result.warnings:
        print(f"警告: {warn}", file=sys.stderr)
    print(f"\n宿主: {result.host}  数据目录: {result.sts2_home}")
    print("下一步: 启动游戏并启用 STS2 MCP 模组 → sts2 ping")
    return 0 if result.ok() else 1


def _cmd_ping() -> int:
    from plugins.sts2 import client as sts2_client

    try:
        payload = sts2_client.ping()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _cmd_status() -> int:
    game = find_game_dir()
    cfg = load_sts2_config()
    lines = [
        f"Hermes home: {display_hermes_home()}",
        f"STS2 base_url: {cfg.get('base_url')}",
        f"character: {cfg.get('character_index', 0)} ({cfg.get('character', 'IRONCLAD')})",
        f"commentary: {cfg.get('commentary')}",
        f"autoplay: {cfg.get('autoplay')}",
    ]
    if game:
        lines.append(f"Game dir: {game}")
        lines.append(f"Mods dir: {mods_dir(game)}")
    else:
        lines.append("Game dir: not found (set STS2_GAME_DIR)")

    try:
        from hermes_cli.config import load_config

        mcp = (load_config().get("mcp_servers") or {}).get("sts2")
        lines.append(f"MCP configured: {bool(mcp)}")
    except Exception:
        lines.append("MCP configured: unknown")

    print("\n".join(lines))
    try:
        from plugins.sts2 import client as sts2_client

        payload = sts2_client.ping()
        print(f"HTTP ping: OK ({payload.get('message', payload)})")
    except Exception as exc:
        print(f"HTTP ping: FAIL ({exc})")
    return 0


def _cmd_crawl_wiki(args: argparse.Namespace) -> int:
    import json

    from plugins.sts2.wiki_crawl.crawler import bundled_dir, crawl_manifest, user_dir

    out_dir = bundled_dir() if getattr(args, "bundle", False) else user_dir()
    result = crawl_manifest(
        categories=getattr(args, "categories", None) or None,
        max_pages=getattr(args, "max_pages", None),
        out_dir=out_dir,
    )
    if getattr(args, "integrate", False):
        from plugins.sts2.wiki_crawl.integrate import integrate_all

        result["integrate"] = integrate_all(write=True)
        _clear_kb_caches()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("errors") else 1


def _cmd_crawl_catalogs(args: argparse.Namespace) -> int:
    import json

    from plugins.sts2.wiki_crawl.integrate import integrate_catalogs

    out = integrate_catalogs(
        write=True,
        max_events=getattr(args, "max_events", None),
        max_relics=getattr(args, "max_relics", None),
        crawl_missing=not getattr(args, "no_crawl", False),
    )
    _clear_kb_caches()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_integrate_wiki(args: argparse.Namespace) -> int:
    import json

    from plugins.sts2.game_flow_kb.store import kb_version as gf_ver
    from plugins.sts2.mechanics_kb.store import kb_version as mech_ver
    from plugins.sts2.wiki_crawl.integrate import integrate_all

    out = integrate_all(write=True)
    _clear_kb_caches()
    out["game_flow_kb_version"] = gf_ver()
    out["mechanics_kb_version"] = mech_ver()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_sync_game_flow(args: argparse.Namespace) -> int:
    import json

    from plugins.sts2.game_flow_kb.store import kb_version, load_catalog

    print(
        json.dumps(
            {"kb_version": kb_version(), "catalog": load_catalog()},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_sync_mechanics(args: argparse.Namespace) -> int:
    import json

    from plugins.sts2.mechanics_kb.store import kb_version

    out: dict = {"kb_version": kb_version()}
    if getattr(args, "wiki", False):
        from plugins.sts2.mechanics_kb.sync import sync_from_wiki

        out["wiki_sync"] = sync_from_wiki(max_pages=int(getattr(args, "max_pages", 20) or 20))
    from plugins.sts2.mechanics_kb.sync import verify_bundled_examples

    out["verify"] = verify_bundled_examples()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["verify"].get("all_ok") else 1


def _cmd_sync_wiki(args: argparse.Namespace) -> int:
    import json

    try:
        if getattr(args, "html_dir", None):
            from plugins.sts2.huiji_kb.sync import sync_from_html_dir

            out = sync_from_html_dir(args.html_dir)
        else:
            from plugins.sts2.huiji_kb.sync import sync_from_api

            out = sync_from_api(
                cookie_file=getattr(args, "cookies", None),
                max_pages=int(getattr(args, "max_pages", 200) or 200),
            )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    if getattr(args, "merge_yaml", False):
        from plugins.sts2.huiji_kb.sync import merge_into_knowledge_yaml

        out["merged_yaml"] = merge_into_knowledge_yaml(act=getattr(args, "act", None))

    print(json.dumps(out, ensure_ascii=False, indent=2))
    from plugins.sts2.huiji_kb.store import kb_stats

    print("\nKB:", kb_stats())
    return 0 if out.get("ok") else 1


def _cmd_install_mod(game_dir: str | None) -> int:
    if game_dir:
        import os

        os.environ["STS2_GAME_DIR"] = game_dir
    root = _repo_root()
    script = root / "scripts" / "install_sts2_mcp_mod.py"
    if not script.is_file():
        print(f"Missing {script}", file=sys.stderr)
        return 1
    py = sys.executable
    venv_py = root / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        py = str(venv_py)
    return subprocess.call([py, str(script)])
