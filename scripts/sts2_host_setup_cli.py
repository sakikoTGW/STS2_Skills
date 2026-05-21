#!/usr/bin/env python3
"""CLI for GUI installer / automation — wraps integrations.host_setup.setup_host."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Configure STS2 for a host platform")
    ap.add_argument("--host", required=True, choices=("standalone", "hermes", "openclaw", "astrbot"))
    ap.add_argument("--repo-root", required=True, help="STS2_Skills root (after extract/copy)")
    ap.add_argument("--game-dir", default="", help="Game install folder")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument(
        "--character",
        "-c",
        type=int,
        default=None,
        help="Optional; default Ironclad (0). Set later in config / WebUI.",
    )
    ap.add_argument("--openclaw-home", default="")
    ap.add_argument("--astrbot-data", default="")
    ap.add_argument("--sts2-home", default="")
    ap.add_argument("--skill-dir", default="")
    ap.add_argument("--install-mod", action="store_true")
    ap.add_argument("--json", action="store_true", help="Emit JSON result on stdout")
    args = ap.parse_args(argv)

    from plugins.sts2.integrations.host_setup import setup_host

    setup_kw: dict = {}
    if args.character is not None:
        setup_kw["character_index"] = args.character

    result = setup_host(
        args.host,
        repo_root_path=args.repo_root,
        python=args.python,
        **setup_kw,
        game_dir=args.game_dir or "",
        sts2_home=args.sts2_home or None,
        openclaw_home=args.openclaw_home or None,
        astrbot_data=args.astrbot_data or None,
        skill_dir=args.skill_dir or None,
        install_mod=args.install_mod,
        skip_pip=True,
    )
    payload = {
        "ok": result.ok(),
        "host": result.host,
        "sts2_home": str(result.sts2_home),
        "config_path": str(result.config_path),
        "messages": result.messages,
        "warnings": result.warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for line in result.messages:
            print(line)
        for warn in result.warnings:
            print(f"WARN: {warn}", file=sys.stderr)
    return 0 if result.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
