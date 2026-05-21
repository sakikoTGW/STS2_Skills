"""Build source + installer zip archives for GitHub Releases."""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TAG = sys.argv[1] if len(sys.argv) > 1 else "v1.3.0"
VER = TAG.lstrip("v")

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "dist",
    "patches",
    "__pycache__",
    ".pytest_cache",
    "hermes_sts2.egg-info",
}
SKIP_SUFFIX = {".pyc"}


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return True
    return path.suffix in SKIP_SUFFIX


def _zip_tree(zf: zipfile.ZipFile, base: Path, arc_prefix: str) -> None:
    for p in base.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(base)
        if _should_skip(rel):
            continue
        zf.write(p, arcname=str(Path(arc_prefix) / rel).replace("\\", "/"))


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    staging = DIST / f"STS2_Skills-{VER}"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(
        ROOT,
        staging,
        ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"),
    )
    src_zip = DIST / f"STS2_Skills-{TAG}.zip"
    inst_zip = DIST / f"STS2_Skills-Installer-{TAG}.zip"
    if src_zip.exists():
        src_zip.unlink()
    if inst_zip.exists():
        inst_zip.unlink()
    with zipfile.ZipFile(src_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        _zip_tree(zf, staging, f"STS2_Skills-{VER}")
    with zipfile.ZipFile(inst_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        _zip_tree(zf, staging, f"STS2_Skills-{VER}")
    shutil.rmtree(staging)
    print(src_zip)
    print(inst_zip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
