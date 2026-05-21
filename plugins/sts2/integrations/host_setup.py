"""One-shot setup for Hermes, OpenClaw, AstrBot, and standalone MCP hosts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from plugins.sts2.integrations.mcp_config import (
    astrbot_mcp_block,
    openclaw_mcp_block,
    openclaw_mcp_set_command,
    repo_root_from_plugin,
)
from plugins.sts2.paths import resolve_game_dir, save_game_dir_hint
from plugins.sts2.platform_home import (
    detect_runtime_host,
    resolve_astrbot_data_dir,
    resolve_openclaw_home,
)

DEFAULT_BASE_URL = "http://127.0.0.1:15526"

# AstrBot: MCP + optional Star plugin may both drive; OpenClaw/Hermes/standalone: one driver.
ENFORCE_SINGLE_DRIVER_BY_HOST: dict[str, bool] = {
    "standalone": True,
    "generic": True,
    "openclaw": True,
    "astrbot": False,
    "hermes": True,
}


@dataclass
class SetupResult:
    host: str
    sts2_home: Path
    config_path: Path
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not any("失败" in w or "错误" in w for w in self.warnings)


def repo_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    root = repo_root_from_plugin()
    if (root / "pyproject.toml").is_file():
        return root
    return Path.cwd().resolve()


def sts2_home_for_host(
    host: str,
    *,
    sts2_home: str | Path | None = None,
    openclaw_home: str | Path | None = None,
    astrbot_data: str | Path | None = None,
) -> Path:
    if sts2_home:
        return Path(sts2_home).expanduser()
    if host == "openclaw":
        oc = resolve_openclaw_home(str(openclaw_home or ""))
        os.environ.setdefault("OPENCLAW_HOME", str(oc))
        return oc / "sts2"
    if host == "astrbot":
        data = resolve_astrbot_data_dir(str(astrbot_data or ""))
        os.environ.setdefault("ASTRBOT_DATA", str(data))
        return data / "sts2"
    if host == "hermes":
        try:
            from hermes_constants import get_hermes_home

            return get_hermes_home() / "sts2"
        except Exception:
            pass
    return Path.home() / ".config" / "sts2"


def write_sts2_config(
    *,
    host: str,
    sts2_home: Path,
    character_index: int,
    base_url: str = DEFAULT_BASE_URL,
    extra: dict[str, Any] | None = None,
) -> Path:
    sts2_home.mkdir(parents=True, exist_ok=True)
    enforce = ENFORCE_SINGLE_DRIVER_BY_HOST.get(host, True)
    section: dict[str, Any] = {
        "base_url": base_url.rstrip("/"),
        "timeout": 15,
        "character": character_index,
        "commentary": "verbose",
        "autoplay": False,
        "pause_on_ask": False if host in ("astrbot", "openclaw") else True,
        "ask_user_on": [] if host in ("astrbot", "openclaw") else [
            "card_reward",
            "relic_select",
            "relic_select_boss",
        ],
        "enforce_single_driver": enforce,
        "autopilot_until_victory": True,
        "study_marathon": host != "standalone",
        "loop_runs": True,
    }
    if host == "astrbot":
        section.update(
            {
                "study_use_llm": True,
                "study_card_pick_llm": False,
                "study_combat_play_llm": True,
                "study_rules_fallback": True,
                "step_interval_seconds": 0.55,
            }
        )
    if extra:
        section.update(extra)
    cfg_path = sts2_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"sts2": section}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    os.environ["STS2_CONFIG_PATH"] = str(cfg_path)
    os.environ["STS2_HOME"] = str(sts2_home)
    return cfg_path


def copy_skill(skill_dst: Path, repo: Path) -> bool:
    for src in (
        repo / "skills" / "slay-the-spire-2",
        repo
        / "plugins"
        / "sts2"
        / "integrations"
        / "openclaw"
        / "skills"
        / "slay-the-spire-2",
        repo
        / "plugins"
        / "sts2"
        / "integrations"
        / "astrbot"
        / "skills"
        / "slay-the-spire-2",
    ):
        if src.is_dir():
            skill_dst.parent.mkdir(parents=True, exist_ok=True)
            if skill_dst.exists():
                shutil.rmtree(skill_dst)
            shutil.copytree(src, skill_dst)
            return True
    return False


def _load_config_file(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    try:
        data = yaml.safe_load(raw)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def _save_config_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in (".yaml", ".yml"):
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    else:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def openclaw_config_candidates(openclaw_home: Path) -> list[Path]:
    return [
        openclaw_home / "openclaw.json",
        openclaw_home / "config.json",
        Path.home() / ".config" / "openclaw" / "config.json",
    ]


def merge_openclaw_mcp(
    *,
    openclaw_home: Path,
    block: dict[str, Any],
    prefer_cli: bool = True,
) -> tuple[Path | None, str]:
    """Merge STS2 into OpenClaw config; try ``openclaw mcp set`` first."""
    if prefer_cli and shutil.which("openclaw"):
        payload = json.dumps(block, ensure_ascii=False)
        try:
            proc = subprocess.run(
                ["openclaw", "mcp", "set", "sts2", payload],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode == 0:
                return None, "openclaw mcp set sts2 (CLI)"
        except (OSError, subprocess.TimeoutExpired):
            pass

    for path in openclaw_config_candidates(openclaw_home):
        if not path.parent.exists() and path != openclaw_home / "openclaw.json":
            continue
        data = _load_config_file(path) if path.is_file() else {}
        mcp = data.setdefault("mcp", {})
        if not isinstance(mcp, dict):
            mcp = {}
            data["mcp"] = mcp
        servers = mcp.setdefault("servers", {})
        if not isinstance(servers, dict):
            servers = {}
            mcp["servers"] = servers
        entry = dict(block)
        entry.setdefault("transport", "stdio")
        servers["sts2"] = entry
        _save_config_file(path, data)
        return path, f"merged mcp.servers.sts2 → {path}"

    fallback = openclaw_home / "mcp.sts2.json"
    fallback.write_text(
        json.dumps(block, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return fallback, (
        f"wrote snippet {fallback}; merge into openclaw.json or run:\n"
        f"  {openclaw_mcp_set_command()}"
    )


def merge_astrbot_mcp(astrbot_data: Path, block: dict[str, Any]) -> Path:
    mcp_json = astrbot_data / "mcp_server.json"
    data: dict[str, Any] = {}
    if mcp_json.is_file():
        try:
            loaded = json.loads(mcp_json.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            pass
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    servers["sts2"] = block
    mcp_json.parent.mkdir(parents=True, exist_ok=True)
    mcp_json.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return mcp_json


def deploy_astrbot_plugin(astrbot_data: Path, repo: Path) -> Path:
    src = repo / "plugins" / "sts2" / "integrations" / "astrbot" / "plugin"
    dst = astrbot_data / "plugins" / "astrbot_plugin_sts2_agent"
    if not src.is_dir():
        return dst
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name.startswith("."):
            continue
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    return dst


def update_astrbot_plugin_config(
    astrbot_data: Path,
    *,
    repo: Path,
    python: str,
    character_index: int,
    game_dir: str = "",
) -> Path:
    cfg_path = astrbot_data / "config" / "astrbot_plugin_sts2_agent_config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    plug: dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                plug = loaded
        except json.JSONDecodeError:
            pass
    plug.update(
        {
            "skills_root": str(repo),
            "astrbot_data_dir": str(astrbot_data),
            "base_url": DEFAULT_BASE_URL,
            "character": character_index,
            "mcp_python": python,
        }
    )
    if game_dir:
        plug["game_dir"] = game_dir
    elif not plug.get("game_dir"):
        found = resolve_game_dir()
        if found:
            plug["game_dir"] = str(found)
    cfg_path.write_text(
        json.dumps(plug, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return cfg_path


def write_standalone_mcp_hint(sts2_home: Path, block: dict[str, Any]) -> Path:
    hint = sts2_home / "mcp.sts2.json"
    hint.write_text(json.dumps(block, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return hint


def _enable_hermes_toolset(cfg: dict[str, Any]) -> None:
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


def _enable_hermes_mcp(cfg: dict[str, Any]) -> None:
    from plugins.sts2.config import load_sts2_config, mcp_server_config

    servers = cfg.setdefault("mcp_servers", {})
    servers["sts2"] = mcp_server_config()
    _ = load_sts2_config()  # ensure env merged before mcp_server_config


def setup_hermes_native(
    *,
    character_index: int,
    repo: Path | None = None,
) -> SetupResult | None:
    """Use ``hermes_cli`` when available; returns None if Hermes CLI is not installed."""
    try:
        from hermes_cli.config import load_config, save_config
        from hermes_constants import display_hermes_home, get_hermes_home

        from plugins.sts2.config import load_sts2_config
    except Exception:
        return None

    cfg = load_config()
    cfg.setdefault("sts2", {}).update(
        {
            k: v
            for k, v in load_sts2_config().items()
            if k
            in (
                "base_url",
                "commentary",
                "autoplay",
                "ask_user_on",
                "pause_on_ask",
                "character",
                "character_index",
                "enforce_single_driver",
            )
        }
    )
    sts2 = cfg.setdefault("sts2", {})
    if isinstance(sts2, dict):
        sts2["character"] = character_index
        sts2["pause_on_ask"] = False
        sts2["ask_user_on"] = []
        sts2["enforce_single_driver"] = True
    _enable_hermes_toolset(cfg)
    if load_sts2_config().get("enable_mcp_on_setup", True):
        _enable_hermes_mcp(cfg)
    save_config(cfg)

    home = get_hermes_home() / "sts2"
    cfg_path = write_sts2_config(
        host="hermes",
        sts2_home=home,
        character_index=character_index,
    )
    r = repo or repo_root()
    skill_dst = get_hermes_home() / "skills" / "slay-the-spire-2"
    msg_skill = (
        str(skill_dst) if copy_skill(skill_dst, r) else "(skill copy skipped)"
    )
    return SetupResult(
        host="hermes",
        sts2_home=home,
        config_path=cfg_path,
        messages=[
            f"Hermes config: {display_hermes_home()}/config.yaml",
            f"STS2 data: {home}",
            f"Skill: {msg_skill}",
        ],
    )


def setup_host(
    host: str,
    *,
    repo_root_path: str | Path | None = None,
    python: str | None = None,
    character_index: int = 0,
    game_dir: str = "",
    sts2_home: str | Path | None = None,
    openclaw_home: str | Path | None = None,
    astrbot_data: str | Path | None = None,
    skill_dir: str | Path | None = None,
    install_mod: bool = False,
    skip_pip: bool = True,
) -> SetupResult:
    host = host or detect_runtime_host()
    repo = repo_root(repo_root_path)
    py = python or sys.executable
    home = sts2_home_for_host(
        host,
        sts2_home=sts2_home,
        openclaw_home=openclaw_home,
        astrbot_data=astrbot_data,
    )
    cfg_path = write_sts2_config(
        host=host,
        sts2_home=home,
        character_index=character_index,
    )
    result = SetupResult(
        host=host,
        sts2_home=home,
        config_path=cfg_path,
        messages=[f"config: {cfg_path}"],
    )

    if game_dir:
        gd = Path(game_dir).expanduser()
        if gd.is_dir():
            save_game_dir_hint(gd)
            os.environ["STS2_GAME_DIR"] = str(gd)
        else:
            result.warnings.append(f"游戏目录不存在: {game_dir}")
    else:
        found = resolve_game_dir()
        if found:
            save_game_dir_hint(found)
            os.environ["STS2_GAME_DIR"] = str(found)
            game_dir = str(found)

    if install_mod and game_dir:
        script = repo / "scripts" / "install_sts2_mcp_mod.py"
        if script.is_file():
            env = {**os.environ, "STS2_GAME_DIR": game_dir}
            proc = subprocess.run([py, str(script)], env=env, cwd=str(repo), check=False)
            if proc.returncode != 0:
                result.warnings.append("install-mod 退出码非 0")
            else:
                result.messages.append(f"mod installed for {game_dir}")
        else:
            result.warnings.append(f"缺少脚本 {script}")

    if not skip_pip:
        proc = subprocess.run(
            [py, "-m", "pip", "install", "-e", f"{repo}[mcp]"],
            cwd=str(repo),
            check=False,
        )
        if proc.returncode != 0:
            result.warnings.append("pip install -e .[mcp] 失败")

    if host == "hermes":
        native = setup_hermes_native(character_index=character_index, repo=repo)
        if native:
            result.messages.extend(native.messages)
            result.warnings.extend(native.warnings)
            return result
        # Fallback: YAML only under ~/.hermes
        hermes_cfg = Path.home() / ".hermes" / "config.yaml"
        hermes_cfg.parent.mkdir(parents=True, exist_ok=True)
        raw: dict[str, Any] = {}
        if hermes_cfg.is_file():
            loaded = yaml.safe_load(hermes_cfg.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded
        sts2 = raw.setdefault("sts2", {})
        if isinstance(sts2, dict):
            sts2.update(
                {
                    "base_url": DEFAULT_BASE_URL,
                    "character": character_index,
                    "pause_on_ask": False,
                    "ask_user_on": [],
                    "enforce_single_driver": True,
                }
            )
        hermes_cfg.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        skill_dst = Path.home() / ".hermes" / "skills" / "slay-the-spire-2"
        if copy_skill(skill_dst, repo):
            result.messages.append(f"skill: {skill_dst}")
        result.messages.append(f"hermes config (no hermes_cli): {hermes_cfg}")
        result.messages.append(
            "安装 Hermes CLI 后运行: hermes sts2 setup"
        )
        return result

    block_kwargs = {
        "repo_root": repo,
        "python": py,
        "sts2_home": str(home),
    }

    if host == "openclaw":
        oc = resolve_openclaw_home(str(openclaw_home or ""))
        os.environ["OPENCLAW_HOME"] = str(oc)
        block = openclaw_mcp_block(openclaw_home=str(oc), **block_kwargs)
        path, how = merge_openclaw_mcp(openclaw_home=oc, block=block)
        result.messages.append(how)
        if path:
            result.messages.append(str(path))
        skill_dst = (
            Path(skill_dir)
            if skill_dir
            else oc / "workspace" / "skills" / "slay-the-spire-2"
        )
        if copy_skill(skill_dst, repo):
            result.messages.append(f"skill: {skill_dst}")
        return result

    if host == "astrbot":
        data = resolve_astrbot_data_dir(str(astrbot_data or ""))
        os.environ["ASTRBOT_DATA"] = str(data)
        deploy_astrbot_plugin(data, repo)
        result.messages.append(f"plugin: {data / 'plugins' / 'astrbot_plugin_sts2_agent'}")
        block = astrbot_mcp_block(astrbot_data=str(data), **block_kwargs)
        mcp_path = merge_astrbot_mcp(data, block)
        result.messages.append(f"MCP: {mcp_path}")
        plug_cfg = update_astrbot_plugin_config(
            data,
            repo=repo,
            python=py,
            character_index=character_index,
            game_dir=game_dir,
        )
        result.messages.append(f"plugin config: {plug_cfg}")
        skill_dst = (
            Path(skill_dir)
            if skill_dir
            else data / "plugins" / "astrbot_plugin_sts2_agent" / "skills" / "slay-the-spire-2"
        )
        if copy_skill(skill_dst, repo):
            result.messages.append(f"skill: {skill_dst}")
        return result

    from plugins.sts2.integrations.mcp_config import generic_mcp_block

    block = generic_mcp_block(platform="generic", **block_kwargs)
    hint = write_standalone_mcp_hint(home, block)
    result.messages.append(f"MCP snippet: {hint}")
    if skill_dir:
        dst = Path(skill_dir) / "slay-the-spire-2"
        if copy_skill(dst, repo):
            result.messages.append(f"skill: {dst}")
    result.messages.append(
        "粘贴 MCP JSON: Cursor 设置 / 或 sts2 integration-config --platform generic --json-only"
    )
    return result
