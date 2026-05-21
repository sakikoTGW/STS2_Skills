"""Multi-turn combat planning: intent history, next-turn hints, coach mechanics, post-play checks."""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from plugins.sts2.combat_brain import incoming_attack_damage
from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)

_COMBAT = frozenset({"monster", "elite", "boss", "hand_select"})
_ATTACK_TYPES = frozenset({"attack", "multi_attack", "multicast", "damage"})
_NON_ATTACK_HINTS = (
    "rest",
    "sleep",
    "stun",
    "defend",
    "buff",
    "debuff",
    "card",
    "escape",
    "休息",
    "防御",
    "眩晕",
    "强化",
    "虚弱",
)

_INTENT_HIST: dict[str, deque[dict]] = {}
_COACH_HINTS: deque[str] = deque(maxlen=12)
_LAST_WARNINGS: list[str] = []


def _coach_log_path() -> Path:
    p = sts2_home() / "combat_coach_hints.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def reset_combat_session() -> None:
    """New battle — clear intent memory."""
    _INTENT_HIST.clear()
    _LAST_WARNINGS.clear()


def _in_combat(state: dict) -> bool:
    return str(state.get("state_type") or "") in _COMBAT


def _battle_round(state: dict) -> int:
    try:
        return int((state.get("battle") or {}).get("round") or 0)
    except (TypeError, ValueError):
        return 0


def _intent_damage(it: dict) -> int:
    for key in ("damage", "base_damage", "min_damage", "max_damage"):
        try:
            return int(it.get(key) or 0)
        except (TypeError, ValueError):
            continue
    label = str(it.get("label") or "")
    m = re.search(r"(\d+)", label)
    if m:
        return int(m.group(1))
    return 0


def _intent_kind(it: dict) -> str:
    typ = str(it.get("type") or "").lower()
    label = str(it.get("label") or "").lower()
    if typ in _ATTACK_TYPES or "attack" in typ or "攻击" in label:
        return "attack"
    if any(h in typ or h in label for h in _NON_ATTACK_HINTS):
        return "non_attack"
    if _intent_damage(it) > 0:
        return "attack"
    return "non_attack"


def _enemy_key(e: dict) -> str:
    return str(e.get("entity_id") or e.get("id") or e.get("name") or "?")


def update_from_state(state: dict) -> None:
    """Snapshot enemy intents each time we read combat state."""
    if not _in_combat(state):
        return
    rnd = _battle_round(state)
    for e in (state.get("battle") or {}).get("enemies") or []:
        if not isinstance(e, dict):
            continue
        key = _enemy_key(e)
        intents = e.get("intents") or []
        if not intents or not isinstance(intents[0], dict):
            continue
        it = intents[0]
        row = {
            "round": rnd,
            "kind": _intent_kind(it),
            "type": str(it.get("type") or ""),
            "label": str(it.get("label") or "")[:80],
            "dmg": _intent_damage(it),
            "hp": e.get("hp"),
        }
        dq = _INTENT_HIST.setdefault(key, deque(maxlen=10))
        if dq and dq[-1].get("round") == rnd and dq[-1].get("label") == row["label"]:
            continue
        dq.append(row)


def predict_next_turn(key: str) -> tuple[str, str]:
    """Return (prediction, coaching line) from intent history."""
    hist = list(_INTENT_HIST.get(key) or [])
    if not hist:
        return "unknown", ""
    last = hist[-1]
    if last["kind"] == "attack":
        return (
            "likely_non_attack",
            "本回合攻击 → 下回合常休息/防/Buff；**勿把易伤/虚弱浪费在它身上**",
        )
    if last["kind"] == "non_attack":
        return (
            "likely_attack",
            "本回合非攻击 → 下回合常打人；**本回合可转向面对高伤怪并留格挡**",
        )
    return "unknown", ""


def _has_surrounded(state: dict) -> bool:
    blob = json.dumps(state, ensure_ascii=False).lower()
    if any(k in blob for k in ("包围", "surround", "flank", "朝向", "orientation", "facing")):
        return True
    for p in (state.get("player") or {}).get("powers") or []:
        if isinstance(p, dict):
            n = str(p.get("name") or p.get("id") or "").lower()
            if "包围" in n or "surround" in n:
                return True
    return False


def _multi_enemy_crab_note(state: dict) -> str:
    enemies = [
        e for e in (state.get("battle") or {}).get("enemies") or [] if isinstance(e, dict)
    ]
    if len(enemies) < 2:
        return ""
    blob = json.dumps(state, ensure_ascii=False).lower()
    if "蟹" not in blob and "crab" not in blob and "crusher" not in blob:
        if not _has_surrounded(state):
            return ""
    lines = [
        "【双怪机制】均匀压血，避免先杀一只触发蟹之怒(+力量+甲)。",
        "有目标牌=转向；优先让**下回合会重击**的怪在正面，背对下回合休息/低伤的怪。",
    ]
    return "\n".join(lines)


def record_coach_hint(text: str) -> None:
    """TUI 教练在战斗中的纠正 — 本战优先。"""
    raw = (text or "").strip()
    if not raw:
        return
    _COACH_HINTS.appendleft(raw[:500])
    row = {"ts": datetime.now(UTC).isoformat(), "text": raw[:2000]}
    try:
        with _coach_log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _coach_block() -> str:
    if not _COACH_HINTS:
        return ""
    return "【本战教练·必读】\n" + "\n".join(f"- {h[:220]}" for h in list(_COACH_HINTS)[:5])


def format_turn_plan_block(state: dict) -> str:
    """Injected into play_brief every combat get_state."""
    if not _in_combat(state):
        return ""
    update_from_state(state)

    battle = state.get("battle") or {}
    turn = str(battle.get("turn") or "").lower()
    if turn and turn not in ("player", "play", "your_turn"):
        return "【敌方回合】等待动画结束，勿出牌。"

    lines = [
        "【出牌前三问·局内多回合视角】",
        "1) 本场战斗按循环还要几回合？T+0/T+1/T+2 各怪做什么（见下方，不只当前）",
        "2) 本步服务「整战少掉血/通关」还是单回合好看？debuff 别给下回合休息的怪",
        "3) 留费/留牌给下回合高伤回合，是否比本回合多打更值得？",
        "4) 包围/多怪：转向谁？蟹怒等机制下是否应均匀压血而非速杀一只？",
    ]

    coach = _coach_block()
    if coach:
        lines.append(coach)

    crab = _multi_enemy_crab_note(state)
    if crab:
        lines.append(crab)

    if _has_surrounded(state):
        lines.append(
            "【朝向】意图伤害通常已含背刺；用有目标牌转向，使**下回合高伤怪在正面**。"
            "不要给即将休息的怪上易伤。"
        )

    lines.append("【各怪意图与下回合推测】")
    for e in (battle.get("enemies") or []):
        if not isinstance(e, dict):
            continue
        key = _enemy_key(e)
        name = e.get("name") or key
        intents = e.get("intents") or []
        cur = ""
        if intents and isinstance(intents[0], dict):
            it = intents[0]
            cur = f"{it.get('type','?')}/{it.get('label','?')} dmg≈{_intent_damage(it)}"
        pred, note = predict_next_turn(key)
        hist = list(_INTENT_HIST.get(key) or [])
        pat = ""
        if len(hist) >= 2:
            kinds = [h["kind"] for h in hist[-4:]]
            pat = f" 近几回合:{'→'.join(kinds)}"
        nxt = note or "样本少，先 wiki/观察一轮"
        lines.append(f"  · {name} [{key}] 本回合:{cur}{pat}")
        lines.append(f"    → {nxt}")

    if _LAST_WARNINGS:
        lines.append("【上一步提醒】" + " | ".join(_LAST_WARNINGS[-3:]))

    lines.append(
        "势不可当/类似能力**不跨战斗**；每战开局需重新打出。"
        "多怪战先 wiki 查循环；搜不到就记意图历史，别瞎猜。"
    )
    return "\n".join(lines)


def check_after_action(
    before: dict,
    after: dict,
    body: dict,
) -> list[str]:
    """Lightweight sanity check after one play_card / end_turn."""
    global _LAST_WARNINGS
    warnings: list[str] = []
    if not _in_combat(before):
        return warnings

    action = str(body.get("action") or "")
    if action == "play_card":
        target = str(body.get("target") or "")
        if target:
            pred, note = predict_next_turn(target)
            if pred == "likely_non_attack" and note:
                warnings.append(f"目标 {target}：{note}")
        try:
            energy = int((after.get("player") or {}).get("energy", 0))
        except (TypeError, ValueError):
            energy = 0
        if energy > 0:
            inc = incoming_attack_damage((after.get("battle") or {}).get("enemies") or [])
            try:
                blk = int((after.get("player") or {}).get("block", 0))
            except (TypeError, ValueError):
                blk = 0
            if inc > blk:
                warnings.append(
                    f"还剩{energy}能量且格挡{blk}<预计伤害{inc}，考虑防御/转向再 end_turn"
                )

    if action == "end_turn":
        inc = incoming_attack_damage((before.get("battle") or {}).get("enemies") or [])
        try:
            blk = int((before.get("player") or {}).get("block", 0))
            hp = int((before.get("player") or {}).get("hp", 0))
        except (TypeError, ValueError):
            blk, hp = 0, 0
        if inc > blk and hp > 0:
            warnings.append(f"结束回合时格挡{blk}低于下回合伤害≈{inc}")

    try:
        from plugins.sts2.combat_line_planner import check_action_vs_plan

        warnings.extend(check_action_vs_plan(before, after, body))
    except Exception:
        pass

    _LAST_WARNINGS = warnings
    return warnings


def observe_transition(prev: dict | None, nxt: dict) -> None:
    """Leave combat → reset; enter combat → fresh session."""
    if not prev:
        return
    pt = str(prev.get("state_type") or "")
    nt = str(nxt.get("state_type") or "")
    if pt not in _COMBAT and nt in _COMBAT:
        reset_combat_session()
    if pt in _COMBAT and nt not in _COMBAT:
        reset_combat_session()
