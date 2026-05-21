"""Create GitHub Release and upload zip (uses git credential token)."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "sakikoTGW/STS2_Skills"
TAG = "v1.3.0"
ROOT = Path(__file__).resolve().parents[1]
SOURCE_ZIP = ROOT / "dist" / f"STS2_Skills-{TAG}.zip"
INSTALLER_ZIP = ROOT / "dist" / f"STS2_Skills-Installer-{TAG}.zip"
NOTES = ROOT / f"RELEASE_NOTES_{TAG}.md"


def _token() -> str:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        check=True,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("No GitHub token from git credential")


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _api(method: str, url: str, token: str, data: bytes | None = None, content_type: str | None = None):
    hdrs = _headers(token)
    if content_type:
        hdrs["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {url} -> {exc.code}: {body[:1200]}") from exc


def _upload_asset(rel: dict, token: str, path: Path, base: str) -> None:
    for asset in rel.get("assets") or []:
        if asset.get("name") == path.name:
            _api("DELETE", f"{base}/releases/assets/{asset['id']}", token)
            print("Removed old asset", path.name)
    upload_url = rel["upload_url"].split("{", 1)[0] + f"?name={path.name}"
    upload_hdrs = _headers(token)
    upload_hdrs["Content-Type"] = "application/zip"
    req = urllib.request.Request(
        upload_url,
        data=path.read_bytes(),
        method="POST",
        headers=upload_hdrs,
    )
    with urllib.request.urlopen(req) as resp:
        asset = json.loads(resp.read())
    print("Uploaded", asset.get("browser_download_url"))


def main() -> int:
    if not SOURCE_ZIP.is_file():
        raise SystemExit(f"Missing zip: {SOURCE_ZIP}")
    token = _token()
    notes = NOTES.read_text(encoding="utf-8") if NOTES.is_file() else f"Release {TAG}"
    base = f"https://api.github.com/repos/{REPO}"

    try:
        rel = _api(
            "POST",
            f"{base}/releases",
            token,
            json.dumps({"tag_name": TAG, "name": TAG, "body": notes}).encode("utf-8"),
        )
        print("Created release", rel["id"])
    except SystemExit as err:
        if "422" not in str(err) and "already_exists" not in str(err).lower():
            # fetch by tag if release exists
            if "422" in str(err):
                rel = _api("GET", f"{base}/releases/tags/{TAG}", token)
                print("Using existing release", rel["id"])
            else:
                raise
        else:
            rel = _api("GET", f"{base}/releases/tags/{TAG}", token)
            print("Using existing release", rel["id"])

    _upload_asset(rel, token, SOURCE_ZIP, base)
    if INSTALLER_ZIP.is_file():
        _upload_asset(rel, token, INSTALLER_ZIP, base)
    print("Release page", rel.get("html_url"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
