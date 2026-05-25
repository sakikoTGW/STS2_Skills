"""Probe whether STS2_Skills environment is already installed for a host."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class InstallReadiness:
    skills_ready: bool
    mod_ready: bool
    host_ready: bool
    pip_ready: bool
    skills_detail: str = ""
    mod_detail: str = ""
    host_detail: str = ""
    pip_detail: str = ""

    @property
    def all_ready(self) -> bool:
        return self.skills_ready and self.mod_ready and self.host_ready and self.pip_ready


def _norm(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def check_skills(skills_dir: str | Path) -> tuple[bool, str]:
    root = Path(skills_dir).expanduser()
    if not root.is_dir():
        return False, "skills_dir missing"
    for rel in ("pyproject.toml", "plugins/sts2/cli.py", "scripts/sts2_mcp_bridge.py"):
        if not (root / rel).is_file():
            return False, "skills incomplete"
    return True, "ok"


def check_mod(game_dir: str | Path) -> tuple[bool, str]:
    from plugins.sts2.paths import mods_dir, resolve_game_dir

    gd = resolve_game_dir(str(game_dir)) if game_dir else None
    if not gd:
        return False, "game not found"
    mdir = mods_dir(gd)
    if (mdir / "STS2_MCP.dll").is_file():
        return True, "ok"
    if any(mdir.glob("*MCP*.dll")):
        return True, "ok"
    return False, "mod missing"


def _sts2_home(host: str, host_path: Path) -> Path:
    if host in ("openclaw", "astrbot", "hermes"):
        return host_path / "sts2"
    return host_path


def check_host(
    host: str,
    host_path: str | Path,
    skills_dir: str | Path,
    game_dir: str | Path,
) -> tuple[bool, str]:
    from plugins.sts2.integrations.mcp_config import mcp_bridge_script

    hp = Path(host_path).expanduser()
    skills = Path(skills_dir).expanduser()
    bridge = mcp_bridge_script(repo_root=skills)
    if not bridge.is_file():
        return False, "bridge missing"

    home = _sts2_home(host, hp)
    hint = home / "game_dir.txt"
    if not hint.is_file():
        return False, "game_dir hint missing"
    saved = hint.read_text(encoding="utf-8").strip()
    if not saved or _norm(saved) != _norm(game_dir):
        return False, "game_dir mismatch"

    bridge_s = str(bridge).replace("\\", "/")
    skills_s = _norm(skills)

    def _text_has(path: Path) -> bool:
        if not path.is_file():
            return False
        text = path.read_text(encoding="utf-8", errors="ignore")
        return bridge_s in text or skills_s in text

    if host == "astrbot":
        mcp = hp / "mcp_server.json"
        plug = hp / "plugins" / "astrbot_plugin_sts2_agent"
        ok = _text_has(mcp) and plug.is_dir()
        return ok, "ok" if ok else "mcp not configured"
    if host == "openclaw":
        for name in ("openclaw.json", "config.json"):
            if _text_has(hp / name):
                return True, "ok"
        return _text_has(hp / "mcp.sts2.json"), "mcp not configured"
    if host == "hermes":
        return _text_has(hp / "config.yaml"), "mcp not configured"
    return _text_has(hp / "mcp.sts2.json") or _text_has(
        Path.home() / ".config" / "sts2" / "mcp.sts2.json"
    ), "mcp not configured"


def check_pip(skills_dir: str | Path, python: str | None = None) -> tuple[bool, str]:
    import subprocess
    import sys

    py = python or sys.executable
    skills = Path(skills_dir).expanduser()
    if not skills.is_dir():
        return False, "skills missing"
    try:
        proc = subprocess.run(
            [py, "-c", "import plugins.sts2"],
            cwd=str(skills),
            capture_output=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0:
            return True, "ok"
    except Exception:
        pass
    return False, "pip/import missing"


def probe_install(
    host: str,
    host_path: str | Path,
    game_dir: str | Path,
    skills_dir: str | Path,
    python: str | None = None,
) -> InstallReadiness:
    sk, sd = check_skills(skills_dir)
    mo, md = check_mod(game_dir)
    ho, hd = check_host(host, host_path, skills_dir, game_dir)
    pi, pd = check_pip(skills_dir, python)
    return InstallReadiness(sk, mo, ho, pi, sd, md, hd, pd)
