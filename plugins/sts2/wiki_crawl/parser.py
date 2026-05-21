"""Lightweight wikitext → facts (no full MW parser)."""

from __future__ import annotations

import re
from typing import Any


def _strip_wiki_noise(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{\{[^}]+\}\}", "", text)
    text = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'''+?", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return text


def extract_summary(wikitext: str, *, max_chars: int = 1200) -> str:
    """First substantive paragraph(s) after infobox/templates."""
    lines: list[str] = []
    for raw in wikitext.split("\n"):
        line = _strip_wiki_noise(raw).strip()
        if not line or line.startswith("|") or line.startswith("!"):
            continue
        if line.startswith("=="):
            if lines:
                break
            continue
        if len(line) < 20:
            continue
        if "Category:" in line or "File:" in line:
            continue
        lines.append(line)
        if sum(len(x) for x in lines) > max_chars:
            break
    out = " ".join(lines)
    return out[:max_chars].strip()


def extract_section_bullets(wikitext: str, section_hint: str, *, limit: int = 8) -> list[str]:
    """Grab bullet lines under a == Section == heading."""
    pattern = re.compile(
        rf"==+\s*{re.escape(section_hint)}[^=]*==+\s*(.*?)(?=\n==|\Z)",
        re.I | re.S,
    )
    m = pattern.search(wikitext)
    if not m:
        return []
    block = m.group(1)
    bullets = []
    for line in block.split("\n"):
        line = _strip_wiki_noise(line).strip()
        if line.startswith("*") or line.startswith("#"):
            bullets.append(line.lstrip("*# ").strip())
        if len(bullets) >= limit:
            break
    return bullets


def extract_tables_simple(wikitext: str) -> list[list[str]]:
    """Wiki table rows as list of cell strings."""
    rows: list[list[str]] = []
    for line in wikitext.split("\n"):
        if not line.strip().startswith("|"):
            continue
        if "----" in line or line.strip().startswith("|-"):
            continue
        cells = [
            _strip_wiki_noise(c).strip()
            for c in line.strip().strip("|").split("|")
        ]
        if any(cells):
            rows.append(cells)
    return rows


def page_to_facts(page_title: str, wikitext: str) -> dict[str, Any]:
    short = page_title.split(":")[-1] if ":" in page_title else page_title
    facts: dict[str, Any] = {
        "page": page_title,
        "short_name": short,
        "summary": extract_summary(wikitext),
        "sections": {},
    }
    for hint in (
        "Interactions",
        "Standard Options",
        "Ascension",
        "Sources",
        "Keywords",
        "Effects",
    ):
        bullets = extract_section_bullets(wikitext, hint)
        if bullets:
            facts["sections"][hint] = bullets
    tables = extract_tables_simple(wikitext)
    if tables:
        facts["tables"] = tables[:12]
    return facts
