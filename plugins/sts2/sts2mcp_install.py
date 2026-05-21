"""Download and install STS2MCP mod assets from GitHub releases."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = "Gennadiyev/STS2MCP"
USER_AGENT = "STS2_Skills/1.0"
MOD_FILES = ("STS2_MCP.dll", "STS2_MCP.json")


def _compat_path() -> Path:
    return Path(__file__).resolve().parents[2] / "compat.yaml"


def default_sts2mcp_tag() -> str | None:
    """Pinned tag from compat.yaml, or None to use latest."""
    path = _compat_path()
    if not path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        tag = str(data.get("sts2mcp_release_tag") or "").strip()
        return tag or None
    except Exception:
        return None


def fetch_release(*, tag: str | None = None) -> dict[str, Any]:
    tag = (tag or os.environ.get("STS2MCP_RELEASE_TAG") or "").strip() or default_sts2mcp_tag()
    if tag:
        url = f"https://api.github.com/repos/{REPO}/releases/tags/{tag}"
    else:
        url = f"https://api.github.com/repos/{REPO}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def release_asset_urls(release: dict[str, Any]) -> dict[str, str]:
    return {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}


def download_mod_assets(
    dest_mods: Path,
    *,
    tag: str | None = None,
) -> str:
    """Download DLL + JSON into dest_mods. Returns installed release tag_name."""
    dest_mods.mkdir(parents=True, exist_ok=True)
    release = fetch_release(tag=tag)
    assets = release_asset_urls(release)
    installed_tag = str(release.get("tag_name") or tag or "?")
    for name in MOD_FILES:
        url = assets.get(name)
        if not url:
            raise RuntimeError(
                f"STS2MCP release {installed_tag} missing asset {name}"
            )
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            (dest_mods / name).write_bytes(resp.read())
    return installed_tag
