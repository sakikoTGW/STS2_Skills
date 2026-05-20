"""Opening bundle / relic bundle (卷轴箱等) — never blind proceed."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from plugins.sts2.safe_parse import normalize_options, option_enabled, option_label


def _bs_dict(state: dict) -> dict:
    raw = state.get("bundle_select")
    return raw if isinstance(raw, dict) else {}


def _bundle_list(bs: dict) -> List[dict]:
    for key in ("bundles", "choices", "options", "offers"):
        raw = bs.get(key)
        if isinstance(raw, list) and raw:
            return [b for b in raw if isinstance(b, dict)]
    return []


def _cards(state: dict, bs: dict) -> List[dict]:
    for key in ("cards",):
        raw = bs.get(key)
        if isinstance(raw, list) and raw:
            return [c for c in raw if isinstance(c, dict)]
    for key in ("card_select", "cards", "offers"):
        raw = state.get(key)
        if isinstance(raw, dict):
            cards = raw.get("cards") or raw.get("options") or []
            if cards:
                return [c for c in cards if isinstance(c, dict)]
        if isinstance(raw, list) and raw:
            return [c for c in raw if isinstance(c, dict)]
    return []


def _score_bundle(blob: dict) -> int:
    text = json.dumps(blob, ensure_ascii=False).lower()
    score = 0
    if any(k in text for k in ("strength", "iron", "愤怒", "力量", "rage")):
        score += 10
    if any(k in text for k in ("strike", "打击", "bash", "痛击")):
        score += 4
    if any(k in text for k in ("defend", "防御", "block", "格挡")):
        score += 3
    return score


def _pick_bundle_index(bundles: List[dict]) -> int:
    if not bundles:
        return 0
    best_i = 0
    best_s = _score_bundle(bundles[0])
    for i, b in enumerate(bundles):
        s = _score_bundle(b)
        if s > best_s:
            best_s = s
            best_i = i
    try:
        return int(bundles[best_i].get("index", best_i))
    except (TypeError, ValueError):
        return best_i


def _action_from_allowed(bs: dict, bundles: List[dict]) -> Optional[dict]:
    allowed = bs.get("allowed_actions") or bs.get("valid_actions") or []
    if isinstance(allowed, str):
        allowed = [allowed]
    if not isinstance(allowed, list):
        return None
    low = [str(a).lower() for a in allowed]
    if any("confirm_bundle" in a for a in low):
        return {"action": "confirm_bundle_selection"}
    if any("cancel_bundle" in a for a in low):
        return {"action": "cancel_bundle_selection"}
    idx = _pick_bundle_index(bundles)
    if any(a in low for a in ("select_bundle", "bundle_select")):
        return {"action": "select_bundle", "index": idx}
    if any("choose_bundle" in a for a in low):
        return {"action": "choose_bundle", "index": idx}
    return None


def decide_bundle_select(state: dict) -> dict:
    """Pick bundle / card — 卷轴箱等；禁止无 proceed 按钮时 proceed。"""
    bs = _bs_dict(state)
    if bs.get("preview_showing") or bs.get("can_confirm"):
        return {"action": "confirm_bundle_selection"}

    bundles = _bundle_list(bs)
    if bundles:
        from_allowed = _action_from_allowed(bs, bundles)
        if from_allowed:
            return from_allowed
        idx = _pick_bundle_index(bundles)
        return {"action": "select_bundle", "index": idx}

    cards = _cards(state, bs)
    if cards:
        from plugins.sts2.decision import _pick_best_card

        pick = _pick_best_card(cards)
        if pick is not None:
            return {"action": "select_card", "index": pick}
        return {"action": "select_card", "index": cards[0].get("index", 0)}

    opts = normalize_options(state.get("options") or bs.get("options") or [])
    enabled = [o for o in opts if option_enabled(o)]
    for prefer in ("take", "select", "choose", "confirm", "continue"):
        for o in enabled:
            lab = option_label(o).lower()
            if prefer in lab or "bundle" in lab:
                ix = o.get("index", 0)
                if "card" in lab:
                    return {"action": "select_card", "index": ix}
                opt = option_label(o)
                if opt:
                    return {"action": "menu_select", "option": opt}
                return {"action": "menu_select", "index": ix}

    if enabled:
        o = enabled[0]
        opt = option_label(o)
        if opt:
            return {"action": "menu_select", "option": opt}

    # 仅当 API 明确说可以 proceed
    if bs.get("can_proceed") is True:
        return {"action": "proceed"}

    return {"action": "__wait__"}


def bundle_select_commentary(state: dict, body: dict) -> str:
    bs = _bs_dict(state)
    n = len(_bundle_list(bs))
    act = str(body.get("action") or "?")
    return f"选包/卷轴({n}项)：{act}，禁止无脑 proceed"
