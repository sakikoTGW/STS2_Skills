#!/usr/bin/env python3
"""Detect default install paths (CLI / wizard). JSON on stdout."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def detect(host: str) -> dict:
    from plugins.sts2.paths import find_game_dir
    from plugins.sts2.integrations.host_setup import sts2_home_for_host
    from plugins.sts2.platform_home import resolve_astrbot_data_dir

    host = host or "standalone"
    if host == "astrbot":
        host_path = resolve_astrbot_data_dir()
    else:
        host_path = sts2_home_for_host(host)

    game = find_game_dir()
    if host == "standalone":
        skills = host_path
    else:
        skills = host_path.parent / "STS2_Skills"
    skills = skills.expanduser()

    py = sys.executable
    if host == "astrbot":
        for cand in (
            Path.home() / "AppData/Local/AstrBot/backend/python/python.exe",
            Path.home() / "AppData/Local/Programs/AstrBot/backend/python/python.exe",
        ):
            if cand.is_file():
                py = str(cand)
                break

    return {
        "host": host,
        "host_path": str(host_path),
        "game_dir": str(game) if game else "",
        "skills_dir": str(skills),
        "python": py,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="standalone")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    payload = detect(args.host)
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.json else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
