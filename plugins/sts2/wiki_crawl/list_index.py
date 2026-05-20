"""Build event/relic indexes from wiki list pages + per-page crawl."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plugins.sts2.wiki_crawl.crawler import (
    bundled_dir,
    crawl_page,
    load_page_facts,
    user_dir,
)
from plugins.sts2.wiki_crawl.parser import extract_summary


def _strip(line: str) -> str:
    line = re.sub(r"\{\{[^}]+\}\}", "", line)
    line = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", line)
    line = re.sub(r"'''+?", "", line)
    return line.strip()

logger = logging.getLogger(__name__)

_API = "https://slaythespire.wiki.gg/api.php"
_UA = "Hermes-STS2-KB-Crawl/1.0"
_EVENTS_LIST = "Slay_the_Spire_2:Events_List"
_RELICS_LIST = "Slay_the_Spire_2:Relics_List"


def _api_parse(page: str, prop: str = "wikitext|links") -> Dict[str, Any]:
    params = urllib.parse.urlencode(
        {"action": "parse", "page": page, "format": "json", "prop": prop}
    )
    req = urllib.request.Request(f"{_API}?{params}", headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8")).get("parse") or {}


def fetch_list_links(list_page: str) -> List[str]:
    """Return full page titles from a list page's parse links."""
    parse = _api_parse(list_page, "links")
    out: List[str] = []
    for link in parse.get("links") or []:
        title = str(link.get("*") or "")
        if not title.startswith("Slay the Spire 2:"):
            continue
        if any(
            x in title
            for x in (
                " List",
                "Category:",
                "Events (",
                "Relics (",
                "Monsters",
                "Cards",
            )
        ):
            continue
        out.append(title.replace("Slay the Spire 2:", "Slay_the_Spire_2:"))
    return out


def _norm_id(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def parse_event_page(wikitext: str, page_title: str) -> Dict[str, Any]:
    """Extract == Options == frames and TS outcome lines."""
    name = page_title.split(":")[-1].replace("_", " ")
    options: List[Dict[str, Any]] = []
    opt_block = re.search(r"== Options ==(.*?)(?=\n== |\Z)", wikitext, re.S)
    if opt_block:
        block = opt_block.group(1)
        for m in re.finditer(r"\{\{Frame\|([^}]+)\}\}(.*?)(?=\{\{Frame\||\Z)", block, re.S):
            label = m.group(1).strip()
            body = m.group(2)
            ts_lines: List[str] = []
            for tag in re.findall(r"\{\{TS\|[^}]+\}\}", body):
                if "||" in tag:
                    text = tag.split("||", 1)[-1].rstrip("}").strip()
                else:
                    text = tag
                text = _strip(text)
                if text:
                    ts_lines.append(text)
            options.append(
                {
                    "label": label,
                    "outcomes": ts_lines[:8],
                    "raw": extract_summary(body, max_chars=400),
                }
            )
    act_hint = ""
    am = re.search(r"found in the \{\{2\|([^}|]+)", wikitext)
    if am:
        act_hint = am.group(1).replace("_", " ")
    return {
        "id": _norm_id(name),
        "name": name,
        "wiki": f"https://slaythespire.wiki.gg/wiki/{page_title.replace(':', '/')}",
        "act_region": act_hint,
        "summary": extract_summary(wikitext, max_chars=500),
        "options": options,
    }


def parse_relic_page(wikitext: str, page_title: str) -> Dict[str, Any]:
    name = page_title.split(":")[-1].replace("_", " ")
    rarity = ""
    for label in ("Common", "Uncommon", "Rare", "Shop", "Boss", "Ancient", "Event", "Special"):
        if f"rarity:{label}" in wikitext or f"|{label}|" in wikitext[:800]:
            rarity = label.lower()
            break
    desc = extract_summary(wikitext, max_chars=600)
    m = re.search(r"\{\{Relic Infobox\|([^|]+)", wikitext)
    if m:
        name = m.group(1).strip()
    return {
        "id": _norm_id(name),
        "name": name,
        "rarity": rarity,
        "wiki": f"https://slaythespire.wiki.gg/wiki/{page_title.replace(':', '/')}",
        "summary": desc,
    }


def _safe_filename(page_title: str) -> str:
    import re

    short = page_title.split(":")[-1]
    return re.sub(r"[^\w.-]+", "_", short)


def _title_variants(page_title: str) -> List[str]:
    out = [page_title]
    if ":" in page_title:
        ns, name = page_title.split(":", 1)
        underscored = f"{ns}:{name.replace(' ', '_')}"
        if underscored not in out:
            out.append(underscored)
    return out


def _get_wikitext(page_title: str, *, crawl_missing: bool) -> str:
    for title in _title_variants(page_title):
        facts = load_page_facts(title)
        if facts and facts.get("wikitext"):
            return str(facts["wikitext"])
    if not crawl_missing:
        return ""
    for title in _title_variants(page_title):
        try:
            facts = crawl_page(title, delay_sec=0.2)
        except (urllib.error.URLError, TimeoutError, KeyError):
            continue
        wt = str(facts.get("wikitext") or "")
        if wt:
            pages_dir = bundled_dir() / "pages"
            pages_dir.mkdir(parents=True, exist_ok=True)
            fn = _safe_filename(page_title) + ".json"
            (pages_dir / fn).write_text(
                json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return wt
    return ""


def build_events_catalog(
    *,
    max_pages: Optional[int] = None,
    crawl_missing: bool = True,
) -> Dict[str, Any]:
    titles = fetch_list_links(_EVENTS_LIST)
    if max_pages:
        titles = titles[:max_pages]
    entries: Dict[str, Any] = {}
    errors: List[str] = []
    for title in titles:
        wt = _get_wikitext(title, crawl_missing=crawl_missing)
        if not wt:
            errors.append(title)
            continue
        ent = parse_event_page(wt, title)
        entries[ent["id"]] = ent
    return {
        "wiki_list": f"https://slaythespire.wiki.gg/wiki/{_EVENTS_LIST.replace(':', '/')}",
        "count": len(entries),
        "entries": entries,
        "errors": errors,
        "errors_count": len(errors),
    }


def build_relics_index(
    *,
    max_pages: Optional[int] = None,
    crawl_missing: bool = True,
) -> Dict[str, Any]:
    titles = fetch_list_links(_RELICS_LIST)
    if max_pages:
        titles = titles[:max_pages]
    entries: Dict[str, Any] = {}
    by_rarity: Dict[str, List[str]] = {}
    errors: List[str] = []
    for i, title in enumerate(titles):
        wt = _get_wikitext(title, crawl_missing=crawl_missing)
        if not wt and (i + 1) % 50 == 0:
            logger.info("relics progress %s/%s", i + 1, len(titles))
        if not wt:
            name = title.split(":")[-1].replace("_", " ")
            rid = _norm_id(name)
            stub_summary = ""
            for variant in _title_variants(title):
                facts = load_page_facts(variant)
                if facts and facts.get("summary"):
                    stub_summary = str(facts["summary"])[:600]
                    break
            entries[rid] = {
                "id": rid,
                "name": name,
                "wiki": f"https://slaythespire.wiki.gg/wiki/{title.replace(':', '/')}",
                "summary": stub_summary,
            }
            if not stub_summary:
                errors.append(title)
            continue
        ent = parse_relic_page(wt, title)
        entries[ent["id"]] = ent
        r = ent.get("rarity") or "unknown"
        by_rarity.setdefault(r, []).append(ent["id"])
    return {
        "wiki_list": f"https://slaythespire.wiki.gg/wiki/{_RELICS_LIST.replace(':', '/')}",
        "count": len(entries),
        "by_rarity": {k: len(v) for k, v in by_rarity.items()},
        "entries": entries,
        "errors": errors,
        "errors_count": len(errors),
    }


def write_catalogs(
    events: Dict[str, Any],
    relics: Dict[str, Any],
    *,
    game_flow_root: Path,
    mech_root: Path,
) -> None:
    game_flow_root.mkdir(parents=True, exist_ok=True)
    mech_root.mkdir(parents=True, exist_ok=True)
    (game_flow_root / "events_catalog.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (mech_root / "relics_index.json").write_text(
        json.dumps(relics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
