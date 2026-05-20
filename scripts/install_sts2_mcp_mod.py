#!/usr/bin/env python3
"""Install STS2MCP mod (DLL + JSON) into the game mods/ folder."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = "Gennadiyev/STS2MCP"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-agent"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def _find_game_dir() -> Path:
    env = (os.environ.get("STS2_GAME_DIR") or "").strip()
    if env:
        path = Path(env)
        if (path / "SlayTheSpire2.exe").is_file():
            return path

    # Repo helper after PYTHONPATH includes project root
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from plugins.sts2.paths import find_game_dir

    found = find_game_dir()
    if found:
        return found
    raise SystemExit(
        "Slay the Spire 2 not found. Set STS2_GAME_DIR to your install folder."
    )


def _save_hint(game_dir: Path) -> None:
    hints: list[Path] = []
    home = os.environ.get("HERMES_HOME", "").strip()
    if home:
        hints.append(Path(home) / "sts2" / "game_dir.txt")
    hints.append(Path.home() / ".hermes" / "sts2" / "game_dir.txt")
    for hint in hints:
        hint.parent.mkdir(parents=True, exist_ok=True)
        hint.write_text(str(game_dir), encoding="utf-8")


def main() -> int:
    game_dir = _find_game_dir()
    mods_dir = game_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(RELEASE_API, headers={"User-Agent": "hermes-agent"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        release = json.loads(resp.read().decode("utf-8"))

    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    for name in ("STS2_MCP.dll", "STS2_MCP.json"):
        if name not in assets:
            print(f"Missing asset {name} in release {release.get('tag_name')}", file=sys.stderr)
            return 1

    print(f"Game: {game_dir}")
    print(f"Release: {release.get('tag_name')}")
    for name in ("STS2_MCP.dll", "STS2_MCP.json"):
        dest = mods_dir / name
        print(f"Downloading {name} ...")
        _download(assets[name], dest)

    _save_hint(game_dir)
    print(f"Installed to {mods_dir}")
    print("Enable the mod in-game (Settings -> Mods), then: curl http://127.0.0.1:15526/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
