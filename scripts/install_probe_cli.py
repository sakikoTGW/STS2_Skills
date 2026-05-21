#!/usr/bin/env python3
"""JSON probe for installer / wizard — skip reinstall when env already matches."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--host-path", required=True)
    ap.add_argument("--game-dir", required=True)
    ap.add_argument("--skills-dir", required=True)
    ap.add_argument("--python", default="")
    args = ap.parse_args()

    from plugins.sts2.install_probe import probe_install

    r = probe_install(
        args.host,
        args.host_path,
        args.game_dir,
        args.skills_dir,
        args.python or None,
    )
    print(json.dumps(asdict(r), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
