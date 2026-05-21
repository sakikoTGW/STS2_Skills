"""Discover Slay the Spire 2 install paths (no hardcoded drive letters)."""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path
from typing import List, Optional


def game_dir_from_env() -> Optional[Path]:
    raw = (os.environ.get("STS2_GAME_DIR") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def repo_root() -> Optional[Path]:
    """STS2_Skills repository root (plugins/sts2/..)."""
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    if (root / "pyproject.toml").is_file() and (here / "decision.py").is_file():
        return root
    return None


def sts2_runtime_bases() -> List[Path]:
    """Directories that may hold game_dir.txt, config.yaml, logs."""
    bases: List[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path.expanduser().resolve()).lower()
        if key not in seen:
            seen.add(key)
            bases.append(path.expanduser())

    for raw in (
        (os.environ.get("STS2_HOME") or "").strip(),
        (os.environ.get("OPENCLAW_HOME") or "").strip(),
        (os.environ.get("ASTRBOT_DATA") or "").strip(),
        (os.environ.get("HERMES_HOME") or "").strip(),
    ):
        if raw:
            add(Path(raw))
    try:
        from hermes_constants import get_hermes_home

        add(get_hermes_home())
    except Exception:
        pass
    for path in (
        Path.home() / ".config" / "sts2",
        Path.home() / ".hermes",
        Path.home() / ".openclaw",
        Path.home() / "AstrBot" / "data",
    ):
        add(path)
    return bases


def resolve_astrbot_data_dir(explicit: str = "") -> Path:
    """AstrBot data root (not a hardcoded user profile path)."""
    raw = (explicit or os.environ.get("ASTRBOT_DATA") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "AstrBot" / "data"


def resolve_game_dir(explicit: str = "") -> Optional[Path]:
    """Plugin config → STS2_GAME_DIR → cache file → Steam discovery."""
    raw = (explicit or os.environ.get("STS2_GAME_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if _looks_like_sts2_install(path):
            return path
    return find_game_dir()


def save_game_dir_hint(game_dir: Path) -> None:
    """Write discovered install path for all active runtime bases."""
    text = str(game_dir.resolve())
    for base in sts2_runtime_bases():
        sts2_base = base if base.name == "sts2" else base / "sts2"
        for hint_parent in (sts2_base, base):
            try:
                hint = hint_parent / "game_dir.txt"
                hint.parent.mkdir(parents=True, exist_ok=True)
                hint.write_text(text, encoding="utf-8")
            except OSError:
                continue


def _read_cached_game_dir() -> Optional[Path]:
    for base in sts2_runtime_bases():
        for hint_parent in (
            base if base.name == "sts2" else base / "sts2",
            base,
        ):
            hint = hint_parent / "game_dir.txt"
            if not hint.is_file():
                continue
            raw = hint.read_text(encoding="utf-8").strip()
            if not raw:
                continue
            path = Path(raw).expanduser()
            if _looks_like_sts2_install(path):
                return path
    return None


def _existing_windows_drives() -> List[str]:
    drives: List[str] = []
    if platform.system() != "Windows":
        return drives
    try:
        import ctypes

        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            if mask & (1 << i):
                drives.append(f"{letter}:\\")
    except Exception:
        pass
    return drives


def _steam_library_paths(steam_path: Optional[Path]) -> List[Path]:
    libs: List[Path] = []
    if steam_path and steam_path.is_dir():
        libs.append(steam_path)
    if not steam_path:
        return libs
    vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf.is_file():
        return libs
    try:
        raw = vdf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return libs
    for match in re.finditer(r'"path"\s+"([^"]+)"', raw):
        p = Path(match.group(1).replace("\\\\", "\\"))
        if p.is_dir() and p not in libs:
            libs.append(p)
    return libs


def _steam_install_roots() -> List[Path]:
    roots: List[Path] = []
    if platform.system() == "Windows":
        steam_path: Optional[Path] = None
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            steam_path_raw, _ = winreg.QueryValueEx(key, "SteamPath")
            winreg.CloseKey(key)
            if steam_path_raw:
                steam_path = Path(str(steam_path_raw))
        except Exception:
            steam_path = None
        roots.extend(_steam_library_paths(steam_path))
        rel = Path("steamapps") / "common" / "Slay the Spire 2"
        for lib in list(roots):
            candidate = lib / rel
            if candidate not in roots:
                roots.append(candidate)
        for drive in _existing_windows_drives():
            for sub in ("Steam", "SteamLibrary"):
                p = Path(drive) / sub
                if p.is_dir() and p not in roots:
                    roots.append(p)
    elif platform.system() == "Darwin":
        home = Path.home()
        roots.append(
            home
            / "Library/Application Support/Steam/steamapps/common/Slay the Spire 2"
        )
    else:
        home = Path.home()
        roots.extend(
            [
                home / ".steam/steam/steamapps/common/Slay the Spire 2",
                home / ".local/share/Steam/steamapps/common/Slay the Spire 2",
            ]
        )
    return roots


def _looks_like_sts2_install(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / "SlayTheSpire2.exe").is_file():
        return True
    if (path / "SlayTheSpire2.app").exists():
        return True
    # Linux data folder layout
    for child in path.iterdir():
        if child.is_dir() and re.match(r"data_sts2_", child.name):
            return True
    return False


def find_game_dir() -> Optional[Path]:
    env = game_dir_from_env()
    if env and _looks_like_sts2_install(env):
        return env

    cached = _read_cached_game_dir()
    if cached:
        return cached

    rel = Path("steamapps") / "common" / "Slay the Spire 2"
    seen: set[str] = set()
    candidates: List[Path] = []
    for root in _steam_install_roots():
        for path in (root, root / rel if root.name != "Slay the Spire 2" else root):
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path)

    for path in candidates:
        if _looks_like_sts2_install(path):
            return path
    return None


def mods_dir(game_dir: Path) -> Path:
    if platform.system() == "Darwin":
        app = game_dir / "SlayTheSpire2.app" / "Contents" / "MacOS" / "mods"
        if app.parent.parent.parent.exists():
            return app
    return game_dir / "mods"
