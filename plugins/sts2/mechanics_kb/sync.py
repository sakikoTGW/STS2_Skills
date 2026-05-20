"""Optional: pull mechanics pages from wiki API into user cache (extends bundled KB)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from plugins.sts2.mechanics_kb.brief import validate_wiki_examples
from plugins.sts2.mechanics_kb.store import bundled_dir, user_dir

logger = logging.getLogger(__name__)

_WIKI_MECHANICS_PAGES = [
    "Vulnerable",
    "Weak",
    "Frail",
    "Strength",
    "Dexterity",
    "Poison",
    "Debuffs",
]


def verify_bundled_examples() -> Dict[str, Any]:
    results = validate_wiki_examples()
    failed = [r for r in results if not r.get("ok")]
    return {
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": failed,
        "all_ok": not failed,
    }


def sync_from_wiki(*, max_pages: int = 20) -> Dict[str, Any]:
    """Best-effort fetch; writes raw snippets + runs wiki_crawl integrate."""
    from plugins.sts2 import client as sts2_client

    out_dir = user_dir() / "wiki_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    synced = []
    for page in _WIKI_MECHANICS_PAGES[:max_pages]:
        q = f"Slay the Spire 2:{page}"
        try:
            status, payload = sts2_client.wiki_search(q, item_type="all", limit=3)
        except Exception as exc:
            logger.debug("wiki_search %s: %s", q, exc)
            continue
        if status != 200:
            continue
        fp = out_dir / f"{page}.json"
        fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        synced.append(page)
    integrate_report: Dict[str, Any] = {}
    try:
        from plugins.sts2.wiki_crawl.integrate import integrate_powers_from_wiki

        integrate_report = integrate_powers_from_wiki(write=True)
    except Exception as exc:
        integrate_report = {"error": str(exc)}
    return {
        "synced": synced,
        "dir": str(out_dir),
        "integrate": integrate_report,
        "verify": verify_bundled_examples(),
    }
