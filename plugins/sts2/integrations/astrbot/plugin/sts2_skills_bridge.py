"""Wire STS2_Skills (STS2MCP) into AstrBot — path, config, LLM patch."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

import yaml

_DEFAULT_BASE_URL = "http://127.0.0.1:15526"

_initialized = False
_stubs_installed = False


def plugin_vendor_root() -> Path:
    return Path(__file__).resolve().parent / "vendor" / "STS2_Skills"


def astrbot_data_dir(plugin_cfg: dict | None = None) -> Path:
    cfg = plugin_cfg or {}
    explicit = (cfg.get("astrbot_data_dir") or cfg.get("astrbot_data") or "").strip()
    try:
        from plugins.sts2.paths import resolve_astrbot_data_dir

        return resolve_astrbot_data_dir(explicit)
    except Exception:
        raw = (explicit or os.environ.get("ASTRBOT_DATA") or "").strip()
        return Path(raw).expanduser() if raw else Path.home() / "AstrBot" / "data"


def default_skills_root(plugin_cfg: dict | None = None) -> Path:
    """STS2_Skills repo: plugin cfg → vendor copy → STS2_SKILLS_ROOT → auto-detect."""
    cfg = plugin_cfg or {}
    raw = (cfg.get("skills_root") or os.environ.get("STS2_SKILLS_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    vend = plugin_vendor_root()
    if (vend / "plugins" / "sts2" / "decision.py").is_file():
        return vend.resolve()
    try:
        from plugins.sts2.paths import repo_root

        root = repo_root()
        if root:
            return root.resolve()
    except Exception:
        pass
    return vend.resolve()


def skills_root_from_cfg(plugin_cfg: dict) -> Path:
    return default_skills_root(plugin_cfg)


def sync_vendor_from_source(src: Path | None = None) -> Path:
    """Copy STS2_Skills tree into plugin vendor/ (one-time / setup)."""
    src = (src or default_skills_root({})).resolve()
    dst = plugin_vendor_root()
    if not (src / "plugins" / "sts2").is_dir():
        raise FileNotFoundError(f"源项目无效: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_dir():
        shutil.rmtree(dst)
    ignore = shutil.ignore_patterns(
        ".git",
        "__pycache__",
        ".venv",
        "tests",
        "*.pyc",
        ".pytest_cache",
    )
    shutil.copytree(src, dst, ignore=ignore)
    return dst


def _install_hermes_stubs(root: Path, data_dir: Path) -> None:
    global _stubs_installed
    if _stubs_installed:
        return
    import json
    import types

    if "tools.registry" not in sys.modules:
        reg = types.ModuleType("tools.registry")

        def tool_result(**kw: Any) -> str:
            return json.dumps({"ok": True, **kw}, ensure_ascii=False)

        def tool_error(msg: str, **kw: Any) -> str:
            return json.dumps({"ok": False, "message": msg, **kw}, ensure_ascii=False)

        reg.tool_result = tool_result  # type: ignore[attr-defined]
        reg.tool_error = tool_error  # type: ignore[attr-defined]
        sys.modules["tools"] = types.ModuleType("tools")
        sys.modules["tools.registry"] = reg

    if "hermes_constants" not in sys.modules:
        hc_path = root / "hermes_constants.py"
        if hc_path.is_file():
            import importlib.util

            spec = importlib.util.spec_from_file_location("hermes_constants", hc_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                sys.modules["hermes_constants"] = mod
        else:
            hc = types.ModuleType("hermes_constants")
            home = data_dir / "sts2"

            def get_hermes_home() -> Path:
                return home

            def display_hermes_home() -> str:
                return str(home)

            hc.get_hermes_home = get_hermes_home  # type: ignore[attr-defined]
            hc.display_hermes_home = display_hermes_home  # type: ignore[attr-defined]
            sys.modules["hermes_constants"] = hc

    _stubs_installed = True


def write_astrbot_sts2_config(plugin_cfg: dict, *, use_llm: bool) -> Path:
    """Write AstrBot sts2/config.yaml (pause_on_ask=false for reward screens)."""
    data = astrbot_data_dir(plugin_cfg)
    sts2_home = data / "sts2"
    sts2_home.mkdir(parents=True, exist_ok=True)
    url = (plugin_cfg.get("base_url") or _DEFAULT_BASE_URL).rstrip("/")
    char_raw = plugin_cfg.get("character", 0)
    char_index = char_raw
    try:
        sys.path.insert(0, str(skills_root_from_cfg(plugin_cfg)))
        from plugins.sts2.character_choice import resolve_character_setting

        char_index, _ = resolve_character_setting(char_raw)
    except Exception:
        try:
            char_index = int(char_raw)
        except (TypeError, ValueError):
            char_index = 0
    section: dict[str, Any] = {
        "base_url": url,
        "character": char_index,
        "timeout": 15,
        "pause_on_ask": False,
        "ask_user_on": [],
        "autopilot_until_victory": True,
        "enforce_single_driver": False,
        "study_marathon": True,
        "study_use_llm": use_llm,
        "study_card_pick_llm": False,
        "study_combat_play_llm": use_llm,
        "study_rules_fallback": True,
        "loop_runs": True,
        "step_interval_seconds": float(plugin_cfg.get("interval", 0.55)),
    }
    cfg_path = sts2_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"sts2": section}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    os.environ["STS2_CONFIG_PATH"] = str(cfg_path)
    os.environ["STS2_HOME"] = str(sts2_home)
    os.environ["ASTRBOT_DATA"] = str(data)
    return cfg_path


def _set_play_env(suffix: str, value: str) -> None:
    for prefix in ("HERMES_STS2_", "STS2_"):
        os.environ[f"{prefix}{suffix}"] = value


def _unset_play_env(suffix: str) -> None:
    for prefix in ("HERMES_STS2_", "STS2_"):
        os.environ.pop(f"{prefix}{suffix}", None)


def apply_astrbot_runtime(plugin_cfg: dict, *, use_llm: bool) -> None:
    data = astrbot_data_dir(plugin_cfg)
    os.environ["ASTRBOT_DATA"] = str(data)
    os.environ.setdefault(
        "STS2_MCP_BASE_URL",
        (plugin_cfg.get("base_url") or _DEFAULT_BASE_URL).rstrip("/"),
    )
    write_astrbot_sts2_config(plugin_cfg, use_llm=use_llm)
    _set_play_env("AGENT_PLAY", "0")
    _set_play_env("NO_MARATHON", "0")
    if use_llm:
        _set_play_env("LLM_PLAY", "1")
        _set_play_env("LLM_AUTOPILOT", "1")
    else:
        _set_play_env("LLM_PLAY", "0")
        _unset_play_env("LLM_AUTOPILOT")


def ensure_skills(
    plugin_cfg: dict,
    *,
    base_url: str | None = None,
) -> Path:
    global _initialized
    root = skills_root_from_cfg(plugin_cfg)
    if not root.is_dir():
        raise FileNotFoundError(
            f"STS2_Skills 目录不存在: {root}\n请先 /sts2ai setup 复制 vendor。"
        )

    data = astrbot_data_dir(plugin_cfg)
    _install_hermes_stubs(root, data)
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)

    merged = dict(plugin_cfg)
    if base_url:
        merged["base_url"] = base_url
    apply_astrbot_runtime(merged, use_llm=bool(plugin_cfg.get("_runtime_use_llm", True)))

    (data / "sts2").mkdir(parents=True, exist_ok=True)
    game = (plugin_cfg.get("game_dir") or "").strip()
    if not game:
        try:
            from plugins.sts2.paths import resolve_game_dir

            found = resolve_game_dir()
            if found:
                game = str(found)
        except Exception:
            pass
    if game:
        os.environ["STS2_GAME_DIR"] = game

    _install_autoplay_card_hook(merged)
    _initialized = True
    return root


def _install_autoplay_card_hook(plugin_cfg: dict) -> None:
    """Wrap study/rule autoplay so card_reward always picks via rules."""
    from plugins.sts2.autoplay import AutoplayController  # noqa: WPS433

    if getattr(AutoplayController, "_astrbot_card_hook", False):
        return

    orig = AutoplayController._single_step
    cfg = dict(plugin_cfg)

    def _wrapped(self: Any) -> dict[str, Any]:
        from .card_pick_force import run_card_flow_until_clear_sync

        forced = run_card_flow_until_clear_sync(cfg)
        if forced and forced.get("success"):
            comm = str(forced.get("commentary") or "")
            if comm:
                try:
                    self._cast(comm[:1200])  # noqa: SLF001
                except Exception:
                    pass
            with self._lock:  # noqa: SLF001
                self._status.steps += 1  # noqa: SLF001
                self._status.last_state_type = str(forced.get("state_type") or "")  # noqa: SLF001
            return forced
        return orig(self)

    AutoplayController._single_step = _wrapped  # type: ignore[method-assign]
    AutoplayController._astrbot_card_hook = True  # type: ignore[attr-defined]


def patch_llm(sync_fn: Callable[..., str]) -> None:
    ensure_skills({})

    import plugins.sts2.llm_util as lu  # noqa: WPS433

    def _patched(
        messages: List[dict],
        *,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> str:
        return sync_fn(messages, max_tokens=max_tokens, temperature=temperature)

    lu.sts2_call_llm = _patched  # type: ignore[method-assign]

    import types

    aux = types.ModuleType("agent.auxiliary_client")

    def call_llm(
        _provider: str,
        *,
        messages: List[dict],
        max_tokens: int = 500,
        temperature: float = 0.3,
        **_: Any,
    ) -> Any:
        text = _patched(messages, max_tokens=max_tokens, temperature=temperature)

        class _Msg:
            content = text

        class _Choice:
            message = _Msg()

        class _Out:
            choices = [_Choice()]

        return _Out()

    aux.call_llm = call_llm  # type: ignore[attr-defined]
    sys.modules["agent"] = types.ModuleType("agent")
    sys.modules["agent.auxiliary_client"] = aux


def set_play_mode(*, use_llm: bool, plugin_cfg: dict | None = None) -> None:
    from plugins.sts2.study_mode import set_study_mode  # noqa: WPS433

    cfg = plugin_cfg or {}
    set_study_mode(use_llm)
    apply_astrbot_runtime(cfg, use_llm=use_llm)


def get_controller(plugin_cfg: dict | None = None):
    cfg = plugin_cfg or {}
    ensure_skills(cfg)
    from plugins.sts2.autoplay import get_controller  # noqa: WPS433

    return get_controller()


def force_unpause_controller(ctrl: Any) -> None:
    try:
        from plugins.sts2.autonomy import clear_user_wait_state  # noqa: WPS433

        clear_user_wait_state()
    except Exception:
        pass
    with ctrl._lock:  # noqa: SLF001
        ctrl._status.paused = False  # noqa: SLF001
        ctrl._status.pause_reason = ""  # noqa: SLF001


def mcp_server_block(plugin_cfg: dict) -> dict[str, Any]:
    import sys as _sys

    from plugins.sts2.integrations.mcp_config import astrbot_mcp_block

    data = astrbot_data_dir(plugin_cfg)
    root = skills_root_from_cfg(plugin_cfg)
    return astrbot_mcp_block(
        repo_root=root,
        python=str(plugin_cfg.get("mcp_python") or _sys.executable),
        base_url=plugin_cfg.get("base_url"),
        sts2_home=str(data / "sts2"),
        astrbot_data=str(data),
    )
