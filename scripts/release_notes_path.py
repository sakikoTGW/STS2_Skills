"""Resolve RELEASE_NOTES_v{ver}.md for a tag or pyproject version."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version_from_tag(tag: str) -> str:
    return tag.lstrip("v")


def version_from_pyproject() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("version missing in pyproject.toml")
    return m.group(1)


def release_notes_path(ver: str) -> Path | None:
    p = ROOT / f"RELEASE_NOTES_v{ver}.md"
    return p if p.is_file() else None


def main() -> int:
    if len(sys.argv) > 1:
        ver = version_from_tag(sys.argv[1]) if sys.argv[1].startswith("v") else sys.argv[1]
    else:
        ver = version_from_pyproject()
    path = release_notes_path(ver)
    if path is None:
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
