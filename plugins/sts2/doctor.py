"""Environment diagnostics for STS2_Skills (no live game required for local checks)."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from plugins.sts2.paths import find_game_dir, mods_dir, repo_root
from plugins.sts2.platform_home import (
    default_sts2_config_path,
    detect_runtime_host,
    resolve_sts2_home,
)


def _check(label: str, ok: bool, detail: str = "", *, hint: str = "") -> dict[str, Any]:
    return {
        "check": label,
        "ok": ok,
        "detail": detail,
        "hint": hint,
    }


def _mod_installed(game: Path | None) -> tuple[bool, str]:
    if not game:
        return False, "未检测到游戏目录"
    mdir = mods_dir(game)
    if (mdir / "STS2_MCP.dll").is_file():
        return True, str(mdir)
    hits = list(mdir.glob("*MCP*.dll"))
    if hits:
        return True, str(hits[0])
    return False, str(mdir)


def _tcp_reachable(base_url: str, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if host in ("127.0.0.1", "localhost"):
            port = parsed.port or 15526
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port}"
    except OSError as exc:
        return False, str(exc)


def _mcp_host_files(host: str, sts2_home: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if host == "openclaw":
        from plugins.sts2.platform_home import resolve_openclaw_home

        oc = resolve_openclaw_home()
        for name in ("openclaw.json", "config.json"):
            p = oc / name
            rows.append(
                _check(
                    f"OpenClaw {name}",
                    p.is_file(),
                    str(p),
                    hint="运行 sts2 setup --host openclaw 或 integration-config --install",
                )
            )
        snippet = oc / "mcp.sts2.json"
        if snippet.is_file():
            rows.append(_check("OpenClaw mcp.sts2.json (snippet)", True, str(snippet)))
    elif host == "astrbot":
        from plugins.sts2.platform_home import resolve_astrbot_data_dir

        data = resolve_astrbot_data_dir()
        mcp = data / "mcp_server.json"
        plug = data / "plugins" / "astrbot_plugin_sts2_agent"
        rows.append(
            _check(
                "AstrBot mcp_server.json",
                mcp.is_file() and '"sts2"' in mcp.read_text(encoding="utf-8"),
                str(mcp),
                hint="sts2 setup --host astrbot --install-mod",
            )
        )
        rows.append(_check("AstrBot Star 插件目录", plug.is_dir(), str(plug)))
    elif host == "hermes":
        hermes_cfg = Path.home() / ".hermes" / "config.yaml"
        ok = False
        detail = "未找到"
        if hermes_cfg.is_file():
            try:
                raw = yaml.safe_load(hermes_cfg.read_text(encoding="utf-8")) or {}
                ok = isinstance(raw.get("sts2"), dict) or bool(
                    (raw.get("mcp_servers") or {}).get("sts2")
                )
                detail = str(hermes_cfg)
            except yaml.YAMLError:
                detail = f"{hermes_cfg} (YAML 解析失败)"
        rows.append(
            _check(
                "Hermes config.yaml (sts2 / mcp_servers.sts2)",
                ok,
                detail,
                hint="hermes sts2 setup 或 sts2 setup --host hermes",
            )
        )
    else:
        snippet = sts2_home / "mcp.sts2.json"
        rows.append(
            _check(
                "standalone MCP 片段",
                snippet.is_file(),
                str(snippet),
                hint="sts2 integration-config --platform generic",
            )
        )
    return rows


def run_doctor(*, json_output: bool = False) -> dict[str, Any]:
    """Run all checks; return structured report."""
    from plugins.sts2.config import load_sts2_config
    from plugins.sts2.version import package_version

    try:
        cfg = load_sts2_config()
    except Exception as exc:
        cfg = {"base_url": "http://127.0.0.1:15526"}
        cfg_error = str(exc)
    else:
        cfg_error = ""

    host = detect_runtime_host()
    sts2_home = resolve_sts2_home(config_log_dir=str(cfg.get("log_dir") or ""))
    config_path = default_sts2_config_path(host)
    if (sts2_home / "config.yaml").is_file():
        config_path = sts2_home / "config.yaml"

    game = find_game_dir()
    mod_ok, mod_detail = _mod_installed(game)
    base_url = str(cfg.get("base_url") or "http://127.0.0.1:15526")
    tcp_ok, tcp_detail = _tcp_reachable(base_url)

    checks: list[dict[str, Any]] = [
        _check("STS2_Skills 版本", True, package_version()),
        _check("检测到的宿主", True, host),
        _check("STS2_HOME", sts2_home.is_dir(), str(sts2_home)),
        _check("配置文件", config_path.is_file(), str(config_path)),
        _check("游戏目录", game is not None, str(game) if game else "", hint="设置 STS2_GAME_DIR"),
        _check("STS2MCP 模组文件", mod_ok, mod_detail),
        _check("API 端口可达", tcp_ok, tcp_detail, hint="启动游戏并启用模组后重试"),
    ]
    if cfg_error:
        checks.append(_check("加载配置", False, cfg_error))

    try:
        from plugins.sts2 import client as sts2_client

        payload = sts2_client.ping()
        checks.append(
            _check("HTTP ping", True, str(payload.get("message", payload)))
        )
    except Exception as exc:
        checks.append(
            _check(
                "HTTP ping",
                False,
                str(exc),
                hint="确认游戏单人模式 + STS2 MCP 模组已开启",
            )
        )

    checks.extend(_mcp_host_files(host, sts2_home))

    bridge = repo_root()
    if bridge:
        script = bridge / "scripts" / "sts2_mcp_bridge.py"
        checks.append(_check("MCP 桥接脚本", script.is_file(), str(script)))

    ok_all = all(c["ok"] for c in checks if c["check"] not in ("HTTP ping", "API 端口可达"))
    critical = [c for c in checks if not c["ok"]]

    report = {
        "ok": ok_all and not critical[:3],
        "runtime_host": host,
        "sts2_home": str(sts2_home),
        "config_path": str(config_path),
        "base_url": base_url,
        "character": cfg.get("character"),
        "character_index": cfg.get("character_index"),
        "checks": checks,
        "next_steps": _next_steps(host, checks),
    }
    if json_output:
        return report
    return report


def _next_steps(host: str, checks: list[dict[str, Any]]) -> list[str]:
    steps: list[str] = []
    by_name = {c["check"]: c for c in checks}

    if not by_name.get("游戏目录", {}).get("ok"):
        steps.append("设置 STS2_GAME_DIR 或在 config.yaml 同目录写入 game_dir.txt")
    if not by_name.get("STS2MCP 模组文件", {}).get("ok"):
        steps.append("运行: sts2 install-mod")
    if not by_name.get("API 端口可达", {}).get("ok"):
        steps.append("启动杀戮尖塔 2 → 单人 → 设置里启用 STS2 MCP 模组")
    if not by_name.get("HTTP ping", {}).get("ok"):
        steps.append("模组开启后执行: sts2 ping")

    if host == "openclaw":
        steps.append("OpenClaw: sts2 setup --host openclaw --install-mod，然后重载 MCP")
    elif host == "astrbot":
        steps.append("AstrBot: WebUI 重载 MCP 与插件 → /sts2ai ping")
    elif host == "hermes":
        steps.append("Hermes: hermes sts2 setup && hermes sts2 ping")
    else:
        steps.append("通用 MCP: sts2 integration-config --platform generic --json-only")

    if not steps:
        steps.append("环境就绪，可 sts2 autoplay study 或让 Agent 调用 MCP 工具")
    return steps


def format_doctor_report(report: dict[str, Any]) -> str:
    lines = [
        f"STS2 doctor — host={report.get('runtime_host')} ok={report.get('ok')}",
        f"  home: {report.get('sts2_home')}",
        f"  config: {report.get('config_path')}",
        f"  api: {report.get('base_url')}",
        f"  character: {report.get('character_index')} ({report.get('character')})",
        "",
    ]
    for row in report.get("checks") or []:
        mark = "OK" if row.get("ok") else "!!"
        line = f"  [{mark}] {row.get('check')}: {row.get('detail')}"
        lines.append(line)
        if not row.get("ok") and row.get("hint"):
            lines.append(f"       → {row['hint']}")
    lines.append("")
    lines.append("建议下一步:")
    for step in report.get("next_steps") or []:
        lines.append(f"  - {step}")
    return "\n".join(lines)


def format_status_report(*, include_doctor: bool = True) -> str:
    """Richer ``sts2 status`` output."""
    from plugins.sts2.config import load_sts2_config
    from plugins.sts2.version import package_version

    cfg = load_sts2_config()
    host = detect_runtime_host()
    home = resolve_sts2_home(config_log_dir=str(cfg.get("log_dir") or ""))
    game = find_game_dir()

    lines = [
        f"sts2-skills {package_version()}",
        f"runtime_host: {host}",
        f"STS2_HOME: {home}",
        f"base_url: {cfg.get('base_url')}",
        f"character: {cfg.get('character_index')} ({cfg.get('character')})",
        f"enforce_single_driver: {cfg.get('enforce_single_driver')}",
        f"commentary: {cfg.get('commentary')}  autoplay: {cfg.get('autoplay')}",
    ]
    if game:
        lines.append(f"game_dir: {game}")
        lines.append(f"mods_dir: {mods_dir(game)}")
    else:
        lines.append("game_dir: (not found — set STS2_GAME_DIR)")

    root = repo_root()
    if root:
        compat_path = root / "compat.yaml"
        if compat_path.is_file():
            raw = yaml.safe_load(compat_path.read_text(encoding="utf-8")) or {}
            tag = raw.get("sts2mcp_release_tag")
            if tag:
                lines.append(f"pinned STS2MCP tag: {tag}")

    if include_doctor:
        lines.append("")
        lines.append(format_doctor_report(run_doctor()))
    return "\n".join(lines)
