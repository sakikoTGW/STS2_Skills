"""Fetch wiki.gg pages via MediaWiki API."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugins.sts2.storage import sts2_home
from plugins.sts2.wiki_crawl.parser import page_to_facts

logger = logging.getLogger(__name__)

_API = "https://slaythespire.wiki.gg/api.php"
_UA = "Hermes-STS2-KB-Crawl/1.0"


def bundled_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "wiki_crawl"


def user_dir() -> Path:
    p = sts2_home() / "knowledge" / "wiki_crawl"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_manifest() -> Dict[str, Any]:
    fp = bundled_dir() / "manifest.json"
    return json.loads(fp.read_text(encoding="utf-8"))


def all_pages(manifest: Dict[str, Any] | None = None) -> List[str]:
    m = manifest or load_manifest()
    pages: List[str] = []
    for cat in (m.get("categories") or {}).values():
        pages.extend(cat)
    return pages


def crawl_page(page_title: str, *, delay_sec: float = 0.35) -> Dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": page_title,
            "format": "json",
            "prop": "wikitext|displaytitle",
        }
    )
    url = f"{_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    time.sleep(delay_sec)
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    parse = data.get("parse") or {}
    wikitext = (parse.get("wikitext") or {}).get("*") or ""
    facts = page_to_facts(page_title, wikitext)
    facts["display_title"] = parse.get("displaytitle", "")
    facts["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    facts["wikitext_chars"] = len(wikitext)
    if wikitext:
        facts["wikitext"] = wikitext[:50000]
    return facts


def _safe_filename(page_title: str) -> str:
    return re.sub(r"[^\w.-]+", "_", page_title.replace("Slay_the_Spire_2:", ""))


def crawl_manifest(
    *,
    categories: Optional[List[str]] = None,
    max_pages: Optional[int] = None,
    out_dir: Path | None = None,
    delay_sec: float = 0.35,
) -> Dict[str, Any]:
    manifest = load_manifest()
    pages: List[str] = []
    cats = categories or list((manifest.get("categories") or {}).keys())
    for cat in cats:
        pages.extend((manifest.get("categories") or {}).get(cat) or [])
    if max_pages:
        pages = pages[: max_pages]

    target = out_dir or user_dir()
    pages_dir = target / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    ok: List[str] = []
    errors: List[str] = []
    index_path = target / "index.json"
    index: Dict[str, Any] = {"version": manifest.get("version"), "pages": {}}
    if index_path.is_file():
        try:
            prev = json.loads(index_path.read_text(encoding="utf-8"))
            index["pages"].update(prev.get("pages") or {})
        except (OSError, json.JSONDecodeError):
            pass

    for title in pages:
        try:
            facts = crawl_page(title, delay_sec=delay_sec)
            fn = _safe_filename(title) + ".json"
            (pages_dir / fn).write_text(
                json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            index["pages"][title] = {
                "file": fn,
                "summary": facts.get("summary", "")[:240],
            }
            ok.append(title)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
            errors.append(f"{title}: {exc}")
            logger.warning("crawl failed %s: %s", title, exc)

    index["ok_count"] = len(ok)
    index["error_count"] = len(errors)
    index["errors"] = errors
    (target / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "ok": ok,
        "errors": errors,
        "dir": str(target),
        "index": str(target / "index.json"),
    }


def load_crawled_index() -> Dict[str, Any]:
    """User crawl overrides bundled pages."""
    idx: Dict[str, Any] = {"pages": {}}
    for root in (bundled_dir(), user_dir()):
        fp = root / "index.json"
        if not fp.is_file():
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            idx["pages"].update(data.get("pages") or {})
        except (OSError, json.JSONDecodeError):
            pass
    return idx


def load_page_facts(page_title: str) -> Optional[Dict[str, Any]]:
    idx = load_crawled_index()
    meta = (idx.get("pages") or {}).get(page_title)
    if not meta:
        short = page_title.split(":")[-1]
        for k, v in (idx.get("pages") or {}).items():
            if k.endswith(short):
                meta = v
                break
    if not meta:
        return None
    fn = meta.get("file")
    for root in (user_dir(), bundled_dir()):
        fp = root / "pages" / str(fn)
        if fp.is_file():
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
    return None
