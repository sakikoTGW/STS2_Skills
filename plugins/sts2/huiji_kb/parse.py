"""Parse huiji wiki HTML (monster pages + index)."""

from __future__ import annotations

import re
import unicodedata
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote

_STRIP_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean_text(text: str) -> str:
    text = unescape(_STRIP_TAGS.sub(" ", text or ""))
    return _WS.sub(" ", text).strip()


def extract_wiki_links(html: str) -> list[str]:
    """Return page titles from /wiki/... hrefs."""
    titles: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'href="(/wiki/([^"#?]+))"', html or ""):
        raw = unquote(m.group(2))
        title = raw.replace("_", " ")
        skip = (
            "Category:",
            "特殊:",
            "File:",
            "Help:",
            "首页",
            "怪物",
            "意图",
            "状态",
            "卡牌",
            "遗物",
        )
        if any(title.startswith(s) or title == s.rstrip(":") for s in skip):
            continue
        if title in seen:
            continue
        seen.add(title)
        titles.append(title)
    return titles


class _TableCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._cur_table: list[list[str]] = []
        self._cur_row: list[str] = []
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        t = tag.lower()
        if t == "table":
            self._in_table = True
            self._cur_table = []
        elif self._in_table and t == "tr":
            self._in_row = True
            self._cur_row = []
        elif self._in_row and t in ("td", "th"):
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th") and self._in_cell:
            self._cur_row.append(_clean_text("".join(self._cell_parts)))
            self._in_cell = False
        elif t == "tr" and self._in_row:
            if self._cur_row:
                self._cur_table.append(self._cur_row)
            self._in_row = False
        elif t == "table" and self._in_table:
            if self._cur_table:
                self.tables.append(self._cur_table)
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)


def _guess_game_id(title: str, html: str) -> str:
    blob = f"{title}\n{html}"
    for pat in (
        r"\b([A-Z][A-Z0-9_]{2,})\b",
        r"entity_id[\"']?\s*[:=]\s*[\"']?([A-Z][A-Z0-9_]+)",
    ):
        for m in re.finditer(pat, blob):
            gid = m.group(1)
            if gid not in ("HTML", "HTTP", "STS2", "API"):
                return gid
    # Pinyin-ish fallback: uppercase title words
    slug = re.sub(r"[^A-Za-z0-9]+", "_", unicodedata.normalize("NFKD", title)).upper().strip("_")
    return slug or "UNKNOWN"


def _parse_intent_row(cells: list[str]) -> dict[str, Any] | None:
    if len(cells) < 2:
        return None
    name = cells[0]
    if not name or name in ("意图", "行动", "名称", "技能"):
        return None
    rest = " | ".join(cells[1:])
    row: dict[str, Any] = {"name": name, "raw": rest}
    rest.lower()
    if any(k in rest for k in ("攻击", "伤害", "damage", "bite", "slash")):
        row["type"] = "attack"
    elif any(k in rest for k in ("格挡", "block", "防御")):
        row["type"] = "block"
    elif any(k in rest for k in ("力量", "虚弱", "易伤", "buff", "debuff", "强化", "咆哮")):
        row["type"] = "buff"
    elif any(k in rest for k in ("睡眠", "眩晕", "stun", "sleep")):
        row["type"] = "debuff"
    else:
        row["type"] = "other"
    dmg = re.search(r"(\d+)\s*点?\s*伤害", rest)
    if dmg:
        row["damage"] = int(dmg.group(1))
    hits = re.search(r"(\d+)\s*次", rest)
    if hits:
        row["hits"] = int(hits.group(1))
    return row


def parse_monster_html(
    title: str,
    html: str,
    *,
    wiki_url: str = "",
) -> dict[str, Any]:
    """Structured monster record from wiki HTML."""
    collector = _TableCollector()
    try:
        collector.feed(html or "")
    except Exception:
        pass

    hp_solo: str | None = None
    intents: list[dict[str, Any]] = []
    infobox: dict[str, str] = {}

    for table in collector.tables:
        header = " ".join(table[0]) if table else ""
        if any(k in header for k in ("意图", "行动", "招式", "技能")):
            for row in table[1:]:
                ent = _parse_intent_row(row)
                if ent:
                    intents.append(ent)
            continue
        # infobox: 2-col key-value
        if len(table[0]) == 2 or all(len(r) == 2 for r in table[:3]):
            for row in table:
                if len(row) >= 2:
                    k, v = row[0], row[1]
                    if k and v:
                        infobox[k] = v
                        if "生命" in k or k.upper() == "HP":
                            hp_solo = v

    # plain text sections
    plain = _clean_text(html)
    pattern_notes = ""
    for label in ("行动模式", "行为", "机制", "特点", "说明"):
        m = re.search(rf"{label}[：:]\s*([^。]+。?)", plain)
        if m:
            pattern_notes = m.group(1).strip()
            break

    from plugins.sts2.huiji_kb.store import normalize_enemy_id

    game_id = normalize_enemy_id(title)
    if not re.match(r"^[A-Z][A-Z0-9_]{2,}$", game_id):
        game_id = _guess_game_id(title, html)
    entry: dict[str, Any] = {
        "id": game_id,
        "wiki_title": title,
        "name_zh": title,
        "wiki_url": wiki_url or f"https://sts2.huijiwiki.com/wiki/{title}",
        "hp_solo": hp_solo,
        "infobox": infobox,
        "intents": intents,
        "pattern": pattern_notes,
        "description": plain[:1200] if plain else "",
        "source": "huijiwiki",
    }
    if intents:
        intent_names = "、".join(i["name"] for i in intents[:6])
        entry["rule"] = f"{title}：意图含{intent_names}；{pattern_notes or '以Wiki意图表为准，勿臆测伤害。'}"[:200]
    elif pattern_notes:
        entry["rule"] = f"{title}：{pattern_notes}"[:200]
    else:
        entry["rule"] = f"{title}：读意图表与机制，低血先防后打。"[:120]

    from plugins.sts2.huiji_kb.loops import attach_behavior_loop

    return attach_behavior_loop(entry)


def title_to_game_id(title: str, aliases: dict[str, str] | None = None) -> str:
    if aliases and title in aliases:
        return aliases[title]
    return _guess_game_id(title, "")
