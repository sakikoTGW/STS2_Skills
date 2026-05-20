"""HTTP client for STS2MCP (https://github.com/Gennadiyev/STS2MCP)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:15526"
DEFAULT_TIMEOUT = 15.0


def get_base_url() -> str:
    from plugins.sts2.config import load_sts2_config

    return str(load_sts2_config().get("base_url", DEFAULT_BASE_URL)).rstrip("/")


def get_timeout() -> float:
    from plugins.sts2.config import load_sts2_config

    return float(load_sts2_config().get("timeout", DEFAULT_TIMEOUT))


def _request(
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> tuple[int, Any]:
    base = get_base_url()
    url = f"{base}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    data: bytes | None = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(
            req, timeout=timeout if timeout is not None else get_timeout()
        ) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Cannot reach STS2MCP at {base} ({exc.reason}). "
            "Start Slay the Spire 2 with STS2_MCP mod enabled (Settings → Mods)."
        ) from exc

    if not raw.strip():
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, {"raw": raw}


def ping() -> dict[str, Any]:
    status, payload = _request("GET", "/")
    if status != 200:
        raise ConnectionError(f"STS2MCP ping failed (HTTP {status}): {payload}")
    if not isinstance(payload, dict):
        raise ConnectionError(f"STS2MCP ping returned unexpected payload: {payload!r}")
    return payload


def get_singleplayer_state(*, fmt: str = "json") -> tuple[int, Any]:
    return _request(
        "GET",
        "/api/v1/singleplayer",
        query={"format": fmt},
    )


def post_singleplayer_action(body: dict[str, Any]) -> tuple[int, Any]:
    if "action" not in body:
        raise ValueError('POST body must include an "action" field')
    act = str(body.get("action") or "")
    # API 不认 __wait__ — 本地跳过，避免 Unknown action 刷屏
    if act == "__wait__":
        return 200, {"status": "ok", "action": "__wait__", "local_skip": True}
    if act == "__pause__":
        return 200, {"status": "ok", "action": "__pause__", "local_skip": True}
    return _request("POST", "/api/v1/singleplayer", body=body)


def wiki_search(
    query: str,
    *,
    item_type: str = "all",
    limit: int = 10,
) -> tuple[int, Any]:
    return _request(
        "GET",
        "/api/v1/wiki",
        query={
            "query": query,
            "item_type": item_type,
            "limit": str(limit),
        },
    )


def get_profile() -> tuple[int, Any]:
    return _request("GET", "/api/v1/profile")


def get_compendium() -> tuple[int, Any]:
    return _request("GET", "/api/v1/compendium")


def get_profiles() -> tuple[int, Any]:
    return _request("GET", "/api/v1/profiles")


def post_profiles(body: dict[str, Any]) -> tuple[int, Any]:
    return _request("POST", "/api/v1/profiles", body=body)
