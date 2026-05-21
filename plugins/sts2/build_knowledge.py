"""Deck archetype knowledge — bundled catalog + web cache + personal build profile."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).resolve().parent / "references" / "builds_catalog.json"
_WEB_SOURCES = (
    "https://slaythespire-2.com/zh/builds",
    "https://sts2front.com/zh-cn/builds/ironclad/",
    "https://www.gamersky.com/tools/sts2bd/",
)


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    try:
        return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("builds_catalog load failed: %s", exc)
        return {"characters": {}, "layer_threats": [], "sources": []}


def _knowledge_dir() -> Path:
    p = sts2_home() / "knowledge"
    p.mkdir(parents=True, exist_ok=True)
    return p


def profile_path() -> Path:
    return _knowledge_dir() / "my_build_profile.json"


def journal_path() -> Path:
    p = sts2_home() / "evolution" / "build_journal.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def web_cache_dir() -> Path:
    p = _knowledge_dir() / "builds_web"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _character(state: dict) -> str:
    run = state.get("run") or {}
    p = state.get("player") or {}
    for k in ("character", "class", "character_id", "selected_character"):
        if run.get(k):
            return str(run[k]).upper().strip()
        if p.get(k):
            return str(p[k]).upper().strip()
    return "IRONCLAD"


def _floor_act(state: dict) -> tuple[int, int]:
    run = state.get("run") or {}
    try:
        return int(run.get("floor") or 0), max(1, int(run.get("act") or 1))
    except (TypeError, ValueError):
        return 0, 1


def list_archetypes(char: str) -> list[dict]:
    cat = load_catalog()
    ch = (cat.get("characters") or {}).get(char.upper()) or {}
    return list(ch.get("archetypes") or [])


def detect_archetype_from_catalog(state: dict) -> tuple[str, str]:
    """Return (archetype_id, source) — ironclad uses ironclad_builds when available."""
    char = _character(state)
    if char in ("IRONCLAD", "IRON_CLAD"):
        from plugins.sts2.ironclad_builds import detect_archetype

        return detect_archetype(state), "ironclad_builds"

    ids: list[str] = []
    player = state.get("player") or {}
    for key in ("deck", "master_deck", "cards", "draw_pile", "discard_pile", "hand"):
        for c in player.get(key) or []:
            if isinstance(c, dict):
                cid = str(c.get("id") or "").upper()
                if cid:
                    ids.append(cid)

    best_id = "tempo"
    best_score = -1
    for arch in list_archetypes(char):
        core = {str(x).upper() for x in (arch.get("core_cards") or [])}
        score = sum(1 for i in ids if i in core)
        if score > best_score:
            best_score = score
            best_id = str(arch.get("id") or "tempo")
    floor, _ = _floor_act(state)
    if best_score < 1 and floor <= 8:
        return "early", "catalog"
    return best_id, "catalog"


def archetype_record(state: dict) -> dict | None:
    char = _character(state)
    aid, _ = detect_archetype_from_catalog(state)
    for arch in list_archetypes(char):
        if str(arch.get("id")) == aid:
            return arch
    return None


def score_card_for_archetype(card_id: str, state: dict) -> float:
    """Higher = better fit for detected archetype."""
    char = _character(state)
    if char in ("IRONCLAD", "IRON_CLAD"):
        from plugins.sts2.ironclad_builds import detect_archetype, offer_pick_score

        floor, _ = _floor_act(state)
        return offer_pick_score(card_id, detect_archetype(state), floor=floor)

    arch = archetype_record(state)
    if not arch:
        return 0.0
    cid = str(card_id or "").upper()
    core = {str(x).upper() for x in (arch.get("core_cards") or [])}
    skip = {str(x).upper() for x in (arch.get("skip_cards") or [])}
    if cid in skip:
        return -40.0
    if cid in core:
        return 80.0
    return 20.0


def layer_threat_lines(state: dict) -> list[str]:
    """Act/floor/boss threats — pick & combat counterplay."""
    floor, act = _floor_act(state)
    cat = load_catalog()
    lines: list[str] = []
    enemies = []
    for e in (state.get("battle") or {}).get("enemies") or []:
        if isinstance(e, dict):
            enemies.append(str(e.get("id") or e.get("name") or "").upper())
    blob = json.dumps(state, ensure_ascii=False).upper()
    for row in cat.get("layer_threats") or []:
        acts = row.get("acts") or []
        if acts and act not in acts:
            continue
        fmax = row.get("floors_max")
        if fmax is not None and floor > int(fmax):
            continue
        if row.get("boss") and floor < 12:
            continue
        keys = [str(x).upper() for x in (row.get("enemies") or [])]
        names = row.get("names") or []
        hit = any(k in blob or k in " ".join(enemies) for k in keys)
        if not hit and not row.get("boss"):
            if act == 1 and floor > 16:
                continue
        label = "、".join(names[:3]) if names else "本层常见威胁"
        lines.append(f"  · [{label}] {row.get('counter', '')}")
        if len(lines) >= 4:
            break
    return lines


def format_layer_threat_block(state: dict) -> str:
    lines = layer_threat_lines(state)
    if not lines:
        return ""
    floor, act = _floor_act(state)
    return (
        f"【层级对策】Act{act} 第{floor}层\n"
        + "\n".join(lines)
        + "\n  抓牌/出牌：缺对策牌时优先补功能，勿为构筑主轴硬拿无关牌。"
    )


def format_build_pick_brief(state: dict, offers: list[dict] | None = None) -> str:
    """Card reward / upgrade screen coaching."""
    char = _character(state)
    aid, src = detect_archetype_from_catalog(state)
    arch = archetype_record(state)
    floor, act = _floor_act(state)

    if char in ("IRONCLAD", "IRON_CLAD"):
        from plugins.sts2.ironclad_builds import archetype_label, build_strategy_brief

        head = build_strategy_brief(state)
        arch_name = archetype_label(aid)
    else:
        arch_name = str(arch.get("name") if arch else aid)
        head = f"【构筑】{char} · 主轴={arch_name} (来源:{src})"
        if arch:
            head += f"\n抓牌: {arch.get('pick', '')}"

    lines = [
        head,
        format_layer_threat_block(state),
        _profile_hint(char),
        _catalog_sources_line(),
    ]
    if offers:
        lines.append("【候选卡·构筑契合分】(越高越贴当前轴)")
        for c in offers[:5]:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id") or "")
            sc = score_card_for_archetype(cid, state)
            tier = ""
            if char in ("IRONCLAD", "IRON_CLAD"):
                from plugins.sts2.ironclad_builds import card_tier_hint

                tier = card_tier_hint(cid)
            lines.append(
                f"  index={c.get('index')} {c.get('name') or cid} "
                f"契合≈{sc:.0f} {tier}".strip()
            )
    lines.append(
        "抓牌四问：①服务通关+控战损的主轴？②补核心还是污染？③本层恶心怪对策？④非拿不可才拿。"
    )
    return "\n".join(x for x in lines if x)


def format_build_combat_hint(state: dict) -> str:
    """Short combat block — play cards for archetype synergy."""
    arch = archetype_record(state)
    if not arch:
        from plugins.sts2.ironclad_builds import combat_playbook_snippet

        return combat_playbook_snippet(state)
    aid, _ = detect_archetype_from_catalog(state)
    if _character(state) in ("IRONCLAD", "IRON_CLAD"):
        from plugins.sts2.ironclad_builds import archetype_label, combat_playbook_snippet

        return (
            f"【构筑出牌】{archetype_label(aid)} — {arch.get('combat', '')}\n"
            + combat_playbook_snippet(state)
        )
    return f"【构筑出牌】{arch.get('name')} — {arch.get('combat', '')}"


def _catalog_sources_line() -> str:
    cat = load_catalog()
    urls = [s.get("url") for s in (cat.get("sources") or []) if s.get("url")]
    if not urls:
        return ""
    return "参考: " + " | ".join(urls[:3])


def _load_profile() -> dict:
    path = profile_path()
    if not path.is_file():
        return {"version": 1, "characters": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "characters": {}}


def _save_profile(data: dict) -> None:
    try:
        profile_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("profile save: %s", exc)


def _profile_hint(char: str) -> str:
    prof = _load_profile()
    ch = (prof.get("characters") or {}).get(char.upper()) or {}
    runs = ch.get("runs") or []
    if not runs:
        return "(个人构筑档案仍空 — 打完一局会自动记录)"
    last = runs[-1]
    return (
        f"【我的构筑】近{len(runs)}局 · 常用轴={ch.get('favorite_archetype', '?')} "
        f"· 最近: {last.get('archetype')} 到第{last.get('floor')}层 "
        f"({'胜' if last.get('win') else '败'})"
    )


def record_card_pick(state: dict, card_id: str, *, index: int = 0) -> None:
    """Session note — which card reinforced the build."""
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "event": "card_pick",
        "card_id": card_id,
        "index": index,
        "archetype": detect_archetype_from_catalog(state)[0],
        "floor": _floor_act(state)[0],
    }
    _append_journal(row)


def _append_journal(row: dict) -> None:
    try:
        with journal_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def refresh_web_build_cache(*, timeout: float = 12.0) -> dict[str, Any]:
    """Fetch public build pages into ~/.hermes/sts2/knowledge/builds_web/ (best-effort)."""
    out: dict[str, Any] = {"fetched": [], "errors": []}
    dest = web_cache_dir()
    for url in _WEB_SOURCES:
        safe = re.sub(r"[^\w]+", "_", url)[:60]
        path = dest / f"{safe}.html"
        try:
            req = Request(url, headers={"User-Agent": "Hermes-STS2-BuildKnowledge/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            path.write_text(raw[:500_000], encoding="utf-8")
            out["fetched"].append({"url": url, "path": str(path), "bytes": len(raw)})
        except Exception as exc:
            out["errors"].append({"url": url, "error": str(exc)})
    return out


def web_digest(*, max_chars: int = 1500) -> str:
    """Snippet from cached web pages for LLM context."""
    parts: list[str] = []
    for path in sorted(web_cache_dir().glob("*.html"))[:3]:
        try:
            text = re.sub(r"<[^>]+>", " ", path.read_text(encoding="utf-8", errors="replace"))
            text = re.sub(r"\s+", " ", text).strip()
            parts.append(text[:max_chars // 3])
        except OSError:
            continue
    return " ".join(parts)[:max_chars]
