#!/usr/bin/env python3
"""Install STS2MCP mod (DLL + JSON) into the game mods/ folder."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _find_game_dir() -> Path:
    env = (os.environ.get("STS2_GAME_DIR") or "").strip()
    if env:
        path = Path(env)
        if (path / "SlayTheSpire2.exe").is_file():
            return path

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
    from plugins.sts2.paths import save_game_dir_hint

    save_game_dir_hint(game_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Install pinned STS2MCP mod into the game")
    ap.add_argument(
        "--tag",
        default=None,
        help="STS2MCP release tag (default: compat.yaml sts2mcp_release_tag)",
    )
    ap.add_argument("--game-dir", default=None, help="Slay the Spire 2 install directory")
    args = ap.parse_args(argv)

    if args.game_dir:
        os.environ["STS2_GAME_DIR"] = args.game_dir

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from plugins.sts2.sts2mcp_install import download_mod_assets

    game_dir = _find_game_dir()
    mods_dir = game_dir / "mods"
    tag = download_mod_assets(mods_dir, tag=args.tag)
    _save_hint(game_dir)
    print(f"Game: {game_dir}")
    print(f"STS2MCP: {tag}")
    print(f"Installed to {mods_dir}")
    print("Enable the mod in-game (Settings -> Mods), then: sts2 ping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
