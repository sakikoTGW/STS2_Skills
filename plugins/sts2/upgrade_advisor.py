"""Smith / Armaments upgrade advisor — card value + post-upgrade payoff."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_PRIORITY_PATH = Path(__file__).resolve().parent / "references" / "upgrade_priority.json"


@lru_cache(maxsize=1)
def _priorities() -> dict:
    try:
        return json.loads(_PRIORITY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"IRONCLAD": {"top": {}, "low": {}, "armaments_targets": []}}


def _char(state: dict) -> str:
    run = state.get("run") or {}
    for k in ("character", "class", "character_id"):
        if run.get(k):
            return str(run[k]).upper()
    return "IRONCLAD"


def _floor_act(state: dict) -> tuple[int, int]:
    run = state.get("run") or {}
    try:
        return int(run.get("floor") or 0), max(1, int(run.get("act") or 1))
    except (TypeError, ValueError):
        return 0, 1


def _hp_ratio(state: dict) -> float:
    p = state.get("player") or {}
    try:
        hp = int(p.get("hp", p.get("current_hp", 1)))
        mx = int(p.get("max_hp", hp) or hp or 1)
        return hp / mx if mx else 1.0
    except (TypeError, ValueError):
        return 1.0


def _desc_delta_hint(card: dict) -> str:
    """Heuristic from description text — upgrade payoff narrative."""
    desc = str(card.get("description") or card.get("raw_description") or "")
    up = str(card.get("upgraded_description") or "")
    blob = f"{desc} {up}"
    hints: list[str] = []
    for pat, msg in (
        (r"\+(\d+)\s*点?格挡", "格挡+\\1"),
        (r"获得\s*(\d+)\s*点?格挡", "格挡+\\1"),
        (r"\+(\d+)\s*点?伤害|造成\s*(\d+)", "伤害提升"),
        (r"易伤", "易伤层数/效果加强"),
        (r"虚弱", "虚弱加强"),
        (r"消耗", "消耗联动加强"),
        (r"每回合", "永久/每回合成长加强"),
        (r"0\s*费|费用.*0", "降费质变"),
    ):
        if re.search(pat, blob, re.I):
            hints.append(msg)
    if card.get("cost") == "0" or str(card.get("cost")) == "0":
        hints.append("0费牌升级=每战免费多收益")
    return "；".join(hints[:3]) if hints else "读 Wiki 描述对比升级前后"


def upgrade_payoff_note(card: dict, state: dict) -> str:
    cid = str(card.get("id") or "").upper()
    char = _char(state)
    pri = (_priorities().get(char) or _priorities().get("IRONCLAD") or {})
    top = pri.get("top") or {}
    low = pri.get("low") or {}
    if cid in top:
        return str(top[cid])
    if cid in low:
        return f"低优先：{low[cid]}"
    return _desc_delta_hint(card)


def score_upgrade(card: dict, state: dict) -> float:
    """Higher = upgrade this card first (smith / Armaments)."""
    if card.get("is_upgraded"):
        return -1000.0

    cid = str(card.get("id") or "").upper()
    char = _char(state)
    floor, act = _floor_act(state)
    pri = (_priorities().get(char) or _priorities().get("IRONCLAD") or {})
    top = pri.get("top") or {}
    low = pri.get("low") or {}

    if cid in low:
        score = 15.0
    elif cid in top:
        score = 90.0 - list(top.keys()).index(cid) * 0.5
    else:
        score = 45.0

    try:
        from plugins.sts2.build_knowledge import score_card_for_archetype

        score += score_card_for_archetype(cid, state) * 0.35
    except Exception:
        pass

    try:
        from plugins.sts2.ironclad_builds import detect_archetype, offer_pick_score

        score += offer_pick_score(cid, detect_archetype(state), floor=floor) * 0.25
    except Exception:
        pass

    ctype = str(card.get("type") or "").lower()
    if ctype == "power" and cid not in low:
        score += 12.0
    if ctype == "attack" and "STRIKE" in cid and floor > 10:
        score -= 25.0
    if "DEFEND" in cid and floor > 8:
        score -= 20.0

    # Armaments in combat: prefer core engines in hand
    if str(state.get("state_type") or "") == "hand_select":
        targets = {str(x).upper() for x in (pri.get("armaments_targets") or [])}
        if cid in targets:
            score += 25.0

    return score


def rank_upgrade_candidates(
    cards: list[dict], state: dict, *, limit: int = 10
) -> list[tuple[dict, float, str]]:
    ranked: list[tuple[dict, float, str]] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        sc = score_upgrade(c, state)
        note = upgrade_payoff_note(c, state)
        ranked.append((c, sc, note))
    ranked.sort(key=lambda x: (-x[1], int(x[0].get("index", 0))))
    return ranked[:limit]


def format_upgrade_brief(state: dict, cards: list[dict], *, context: str = "") -> str:
    """Inject into play_brief for smith / card_select / hand_select upgrade."""
    if not cards:
        return "【敲牌】无候选卡列表。"

    ranked = rank_upgrade_candidates(cards, state)
    floor, act = _floor_act(state)
    hp_pct = int(100 * _hp_ratio(state))

    lines = [
        f"【敲牌·升级决策】{context or '选一张升级'} · Act{act} 第{floor}层 · HP{hp_pct}%",
        "原则：①牌对构筑主轴的长期价值 ②升级后多打的回合收益（非单次面板）③已+的勿敲",
        "④打击/基础防后期优先删而非敲；力量/消耗核心优先敲",
    ]
    try:
        from plugins.sts2.run_objective import map_route_objective_lines

        lines.insert(1, map_route_objective_lines(state)[0].replace("路线", "敲牌也服务整局"))
    except Exception:
        pass

    best = ranked[0] if ranked else None
    if best and best[1] > 0:
        c, sc, note = best
        lines.append(
            f"★ 推荐 index={c.get('index')} {c.get('name') or c.get('id')} "
            f"(分{sc:.0f}) → {note}"
        )

    lines.append("候选排序（分越高越值得敲）:")
    for c, sc, note in ranked[:8]:
        mark = "+" if c.get("is_upgraded") else " "
        lines.append(
            f"  {mark} index={c.get('index')} {c.get('name') or c.get('id')} "
            f"分{sc:.0f} | 敲后收益: {note}"
        )

    st = str(state.get("state_type") or "")
    if st == "hand_select":
        lines.append(
            "→ combat_select_card(card_index) 再 combat_confirm_selection；"
            "优先敲未+的核心引擎（见★）"
        )
    elif st == "card_select":
        lines.append(
            "→ select_card(index) 点选 → confirm_selection；预览屏先看清升级后描述"
        )
    else:
        lines.append("→ 营火选 smith 后对本列表选 index 升级")

    return "\n".join(lines)


def format_rest_site_brief(state: dict) -> str:
    """Heal vs smith vs other — includes whether deck has good upgrade target."""
    from plugins.sts2.safe_parse import normalize_options, option_enabled, option_label

    rs = state.get("rest_site") or {}
    raw = rs.get("options") or state.get("options") or []
    opts = [o for o in normalize_options(raw) if option_enabled(o)]
    hp_pct = _hp_ratio(state)
    floor, act = _floor_act(state)

    try:
        from plugins.sts2.game_flow_kb.ascension import rest_heal_amount

        rh = rest_heal_amount(state)
        heal_line = (
            f"wiki休息预估 +{rh['heal']}HP → {rh['hp_after']}/{rh['max_hp']}"
            f"（30%最大生命向下取整"
            + (f"+{rh['max_hp_gain']}MaxHP遗物" if rh.get("max_hp_gain") else "")
            + "）"
        )
    except Exception:
        heal_line = "wiki: 休息=30%最大生命(向下取整)"

    lines = [
        f"【营火】Act{act} 第{floor}层 · HP{int(100*hp_pct)}%",
        heal_line,
        "决策层级：通关>控战损 — 低血先 heal，否则评估 smith；进阶2不减营火治疗",
    ]

    # Deck cards that could be upgraded if we pick smith
    deck_cards: list[dict] = []
    player = state.get("player") or {}
    for key in ("deck", "master_deck", "cards"):
        for c in player.get(key) or []:
            if isinstance(c, dict) and not c.get("is_upgraded"):
                deck_cards.append(c)
    ranked = rank_upgrade_candidates(deck_cards, state, limit=3)
    if ranked and ranked[0][1] >= 55:
        c, sc, note = ranked[0]
        lines.append(
            f"若敲牌：最值得敲 [{c.get('name') or c.get('id')}] 分{sc:.0f} — {note}"
        )
    elif deck_cards:
        lines.append("若敲牌：无S级目标，优先 heal 或删牌，别浪费敲位")
    else:
        lines.append("牌组未同步到 API — 进 smith 后再看升级列表")

    lines.append("选项:")
    for o in opts[:6]:
        lab = option_label(o) or "?"
        oid = str(o.get("id") or o.get("type") or "").lower()
        hint = ""
        if "heal" in oid or "rest" in oid or "医" in lab or "休" in lab:
            hint = " → 低血必选" if hp_pct < 0.55 else " → 血够可跳过"
        elif "smith" in oid or "upgrade" in oid or "锻" in lab or "敲" in lab:
            if hp_pct < 0.58:
                hint = " → HP<58% 通常先 heal，再考虑敲牌"
            elif ranked and ranked[0][1] >= 70:
                hint = " → 有好敲目标，值得"
            else:
                hint = " → 无高价值敲目标时不如 heal/删牌"
        elif "remove" in oid or "删" in lab:
            hint = " → 删打击/防御污染"
        lines.append(f"  index={o.get('index')} {lab}{hint}")

    lines.append('→ sts2_act {"action":"choose_rest_option","index":N}')
    return "\n".join(lines)


def is_upgrade_screen(state: dict) -> bool:
    st = str(state.get("state_type") or "")
    if st == "hand_select":
        hs = state.get("hand_select") or {}
        prompt = str(hs.get("prompt") or hs.get("mode") or "")
        return "upgrade" in prompt.lower() or "升级" in prompt
    if st == "card_select":
        cs = state.get("card_select") or {}
        prompt = str(cs.get("prompt") or state.get("prompt") or "")
        if "upgrade" in prompt.lower() or "升级" in prompt or "smith" in prompt.lower():
            return True
    return False


def collect_upgrade_candidates(state: dict) -> list[dict]:
    from plugins.sts2.reward_cards import offer_reward_cards

    if str(state.get("state_type") or "") == "hand_select":
        hs = state.get("hand_select") or {}
        return [c for c in (hs.get("cards") or []) if isinstance(c, dict)]
    return [c for c in (offer_reward_cards(state) or []) if isinstance(c, dict)]
