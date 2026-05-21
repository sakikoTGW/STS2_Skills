"""Sync monster KB from huiji wiki or local HTML dumps."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from plugins.sts2.huiji_kb.client import HuijiWikiClient, HuijiWikiError
from plugins.sts2.huiji_kb.parse import parse_monster_html
from plugins.sts2.huiji_kb.store import kb_stats, save_user_store

logger = logging.getLogger(__name__)

INDEX_TITLE = "怪物"
DEFAULT_CATEGORIES = ("怪物", "第一幕怪物", "第二幕怪物", "第三幕怪物")


def _cookie_default() -> Path | None:
    from plugins.sts2.storage import sts2_home

    p = sts2_home() / "huiji_cookies.txt"
    return p if p.is_file() else None


def discover_titles(
    client: HuijiWikiClient,
    *,
    categories: list[str] | None = None,
) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    cats = categories or list(DEFAULT_CATEGORIES)
    for cat in cats:
        try:
            for t in client.category_members(cat, limit=500):
                if t not in seen:
                    seen.add(t)
                    titles.append(t)
        except HuijiWikiError as exc:
            logger.debug("category %s failed: %s", cat, exc)
    if not titles:
        try:
            for t in client.links_on_page(INDEX_TITLE):
                if t not in seen:
                    seen.add(t)
                    titles.append(t)
        except HuijiWikiError:
            pass
    return titles


def sync_from_api(
    *,
    cookie_file: str | Path | None = None,
    categories: list[str] | None = None,
    max_pages: int = 200,
    delay_sec: float = 0.4,
) -> dict[str, Any]:
    cookie = cookie_file or _cookie_default()
    client = HuijiWikiClient(cookie_file=cookie, delay_sec=delay_sec)
    titles = discover_titles(client, categories=categories)
    if not titles:
        raise HuijiWikiError(
            "未能列出任何怪物页。请配置 cookies 或使用 --html-dir 导入。"
        )

    entries: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for i, title in enumerate(titles[:max_pages]):
        try:
            html = client.parse_page(title)
            ent = parse_monster_html(title, html)
            eid = str(ent.get("id") or "").upper()
            if eid and eid != "UNKNOWN":
                entries[eid] = ent
        except Exception as exc:
            errors.append(f"{title}: {exc}")
            logger.debug("sync skip %s: %s", title, exc)

    if entries:
        save_user_store(entries, source="huijiwiki_api")
    return {
        "ok": bool(entries),
        "titles_found": len(titles),
        "synced": len(entries),
        "errors": errors[:20],
        "stats": kb_stats(),
    }


def sync_from_html_dir(html_dir: str | Path) -> dict[str, Any]:
    root = Path(html_dir)
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    entries: dict[str, dict[str, Any]] = {}
    for fp in sorted(root.glob("*.html")):
        html = fp.read_text(encoding="utf-8", errors="replace")
        title = fp.stem.replace("_", " ")
        import re as _re

        hm = _re.search(r"<h1[^>]*>([^<]+)</h1>", html, _re.I)
        if hm:
            title = _re.sub(r"\s+", " ", hm.group(1)).strip() or title
        ent = parse_monster_html(title, html)
        eid = str(ent.get("id") or "").upper()
        stem_id = fp.stem.upper().replace("-", "_")
        if eid == "UNKNOWN" and re.match(r"^[A-Z][A-Z0-9_]{2,}$", stem_id):
            ent["id"] = stem_id
            eid = stem_id
        if eid and eid != "UNKNOWN":
            entries[eid] = ent
    if entries:
        save_user_store(entries, source=f"html_dir:{root}")
    return {"ok": bool(entries), "synced": len(entries), "stats": kb_stats()}


def merge_into_knowledge_yaml(*, act: int | None = None) -> int:
    """Push huiji entries into ~/.hermes/sts2/knowledge/enemies.yaml for agent."""
    from plugins.sts2.huiji_kb.store import list_enemies, to_knowledge_entry
    from plugins.sts2.knowledge import upsert_entry

    n = 0
    for ent in list_enemies(act=act):
        kid = str(ent.get("id") or "")
        if not kid:
            continue
        upsert_entry("enemies", kid, to_knowledge_entry(ent))
        n += 1
    return n
