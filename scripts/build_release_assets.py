"""Build source + installer zip archives for GitHub Releases."""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
def _default_tag() -> str:
    import re

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    v = m.group(1) if m else "0.0.0"
    return f"v{v}"


TAG = sys.argv[1] if len(sys.argv) > 1 else _default_tag()
VER = TAG.lstrip("v")

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "patches",
    "__pycache__",
    ".pytest_cache",
    "sts2_skills.egg-info",
    "hermes_sts2.egg-info",
    "install_stub",
    "bin",
    "obj",
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
    if src_zip.exists():
        src_zip.unlink()
    with zipfile.ZipFile(src_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        _zip_tree(zf, staging, f"STS2_Skills-{VER}")
    shutil.rmtree(staging)

    mod_dir = ROOT / "mods" / "STS2MCP"
    mod_ver = "unknown"
    ver_file = mod_dir / "VERSION"
    if ver_file.is_file():
        mod_ver = ver_file.read_text(encoding="utf-8").strip().lstrip("v")
    mod_zip = DIST / f"STS2MCP-mod-{mod_ver}.zip"
    if mod_zip.exists():
        mod_zip.unlink()
    with zipfile.ZipFile(mod_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("STS2_MCP.dll", "STS2_MCP.json", "VERSION", "README.md"):
            p = mod_dir / name
            if p.is_file():
                zf.write(p, arcname=name)
    print(src_zip)
    print(mod_zip)
    exe = ROOT / "sts2skill.exe"
    if exe.is_file():
        print(f"(Release 附件) {exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
