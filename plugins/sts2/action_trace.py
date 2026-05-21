"""Infer in-game actions and effects by diffing consecutive API states."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

from plugins.sts2.combat_brain import incoming_attack_damage


@dataclass
class InferredAction:
    kind: str
    detail: str
    effects: list[str] = field(default_factory=list)


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _hand_keys(state: dict) -> list[tuple[str, str, int]]:
    out = []
    for c in (state.get("player") or {}).get("hand") or []:
        out.append(
            (
                str(c.get("id") or ""),
                str(c.get("name") or "?"),
                _int(c.get("index"), -1),
            )
        )
    return out


def _pile_tail(state: dict, pile: str) -> list[str]:
    names = []
    for c in (state.get("player") or {}).get(pile) or []:
        names.append(str(c.get("name") or c.get("id") or "?"))
    return names


def _potions(state: dict) -> list[dict | None]:
    pots = (state.get("player") or {}).get("potions") or []
    slots = _int((state.get("player") or {}).get("max_potion_slots"), 3)
    out: list[dict | None] = [None] * max(slots, len(pots))
    for p in pots:
        if not isinstance(p, dict):
            continue
        slot = _int(p.get("slot"), len(out))
        if 0 <= slot < len(out):
            out[slot] = p
        else:
            out.append(p)
    return out


def _enemy_lines(state: dict) -> list[str]:
    lines = []
    for e in (state.get("battle") or {}).get("enemies") or []:
        name = e.get("name") or e.get("id") or "敌人"
        hp = _int(e.get("hp"))
        mx = _int(e.get("max_hp"), hp)
        blk = _int(e.get("block"))
        intents = e.get("intents") or []
        intent = ""
        if intents:
            intent = str(intents[0].get("label") or intents[0].get("type") or "")
        lines.append(f"{name} {hp}/{mx} 格挡{blk} 意图{intent or '?'}")
    return lines


def _status_names(state: dict) -> list[str]:
    return [
        str(p.get("name") or p.get("id"))
        for p in (state.get("player") or {}).get("status") or []
        if isinstance(p, dict)
    ]


def infer_player_actions(before: dict, after: dict) -> list[InferredAction]:
    """Best-effort reconstruction of what the human did between two polls."""
    if not before or not after:
        return []

    actions: list[InferredAction] = []
    bp = before.get("player") or {}
    after.get("player") or {}
    bb = before.get("battle") or {}
    ab = after.get("battle") or {}

    bt = str(bb.get("turn") or "").lower()
    at = str(ab.get("turn") or "").lower()
    if bt == "player" and at == "enemy":
        actions.append(InferredAction("end_turn", "结束回合"))

    # Potions
    bpots = _potions(before)
    apots = _potions(after)
    for slot in range(max(len(bpots), len(apots))):
        b = bpots[slot] if slot < len(bpots) else None
        a = apots[slot] if slot < len(apots) else None
        if b and not a:
            actions.append(
                InferredAction(
                    "use_potion",
                    f"用药水「{b.get('name', '?')}」(槽位{slot})",
                )
            )
        elif b and a and b.get("id") != a.get("id"):
            actions.append(
                InferredAction(
                    "use_potion",
                    f"用药水「{b.get('name', '?')}」→ 槽位变为「{a.get('name', '?')}」",
                )
            )

    # Cards left hand
    before_hand = _hand_keys(before)
    after_hand = _hand_keys(after)
    after_set = {(i, n) for _, n, i in after_hand}
    for cid, name, idx in before_hand:
        if (idx, name) not in after_set and (cid, name) not in {(a, n) for a, n, _ in after_hand}:
            ctype = ""
            for c in bp.get("hand") or []:
                if c.get("index") == idx:
                    ctype = str(c.get("type") or "")
                    break
            actions.append(
                InferredAction(
                    "play_card",
                    f"打出「{name}」({ctype or '牌'})",
                )
            )

    # New cards on discard (backup when hand already refreshed)
    bdisc = _pile_tail(before, "discard_pile")
    adisc = _pile_tail(after, "discard_pile")
    if len(adisc) > len(bdisc):
        for name in adisc[len(bdisc) :]:
            if not any(a.kind == "play_card" and name in a.detail for a in actions):
                actions.append(InferredAction("play_card", f"打出「{name}」(进弃牌堆)"))

    # Map / event / reward screens
    bst = str(before.get("state_type") or "")
    ast = str(after.get("state_type") or "")
    if bst == "map" and ast != "map":
        actions.append(InferredAction("map_travel", f"离开地图 → 进入 {ast}"))
    if bst == "event" and ast != "event":
        ev = before.get("event") or {}
        actions.append(
            InferredAction(
                "event_choice",
                f"完成事件「{ev.get('event_name', ev.get('event_id', '?'))}」→ {ast}",
            )
        )
    if bst == "card_reward" and ast != "card_reward":
        actions.append(InferredAction("pick_card", "完成选牌奖励"))
    if bst in ("relic_select", "relic_select_boss") and ast not in (
        "relic_select",
        "relic_select_boss",
    ):
        actions.append(InferredAction("pick_relic", "完成遗物选择"))

    return actions


def infer_effects(before: dict, after: dict) -> list[str]:
    """Observable combat / run effects between polls."""
    if not before or not after:
        return []

    effects: list[str] = []
    bp = before.get("player") or {}
    ap = after.get("player") or {}

    hp0, hp1 = _int(bp.get("hp")), _int(ap.get("hp"))
    if hp1 < hp0:
        effects.append(f"你受到 {hp0 - hp1} 伤害 (HP {hp0}→{hp1})")
    elif hp1 > hp0:
        effects.append(f"你回复 {hp1 - hp0} 生命 (HP {hp0}→{hp1})")

    blk0, blk1 = _int(bp.get("block")), _int(ap.get("block"))
    if blk1 > blk0:
        effects.append(f"获得 {blk1 - blk0} 格挡 (总计{blk1})")
    elif blk1 < blk0:
        effects.append(f"格挡消耗/减少 {blk0}→{blk1}")

    en0, en1 = _int(bp.get("energy")), _int(ap.get("energy"))
    if en1 != en0 and str((after.get("battle") or {}).get("turn")).lower() == "player":
        effects.append(f"能量 {en0}→{en1}")

    # Enemy damage
    be = (before.get("battle") or {}).get("enemies") or []
    ae = (after.get("battle") or {}).get("enemies") or []
    for i, e0 in enumerate(be):
        if i >= len(ae):
            break
        e1 = ae[i]
        name = e0.get("name") or e0.get("id") or f"敌人{i}"
        h0, h1 = _int(e0.get("hp")), _int(e1.get("hp"))
        if h1 < h0:
            effects.append(f"对 {name} 造成 {h0 - h1} 伤害 (剩 {h1} HP)")
        b0, b1 = _int(e0.get("block")), _int(e1.get("block"))
        if b1 > b0:
            effects.append(f"{name} 获得 {b1 - b0} 格挡")

    if len(ae) < len(be):
        effects.append(f"敌人数量 {len(be)}→{len(ae)} (可能击杀)")

    # Incoming intent context after enemy phase
    if str((before.get("battle") or {}).get("turn")).lower() == "enemy":
        inc = incoming_attack_damage(ae)
        if inc > 0:
            effects.append(f"敌人回合威胁约 {inc} 伤害")

    # Buffs / powers
    s0, s1 = set(_status_names(before)), set(_status_names(after))
    gained = s1 - s0
    lost = s0 - s1
    if gained:
        effects.append("获得状态: " + ", ".join(sorted(gained)))
    if lost:
        effects.append("失去状态: " + ", ".join(sorted(lost)))

    br = before.get("run") or {}
    ar = after.get("run") or {}
    if _int(br.get("gold")) != _int(ar.get("gold")):
        effects.append(f"金币 {_int(br.get('gold'))}→{_int(ar.get('gold'))}")

    if br.get("floor") != ar.get("floor"):
        effects.append(f"到达第 {_int(ar.get('floor'))} 层")

    return effects


def format_action_trace(before: dict, after: dict) -> str:
    """Human-readable block for MCP / live_feed / agent chat."""
    actions = infer_player_actions(before, after)
    effects = infer_effects(before, after)
    if not actions and not effects:
        return ""

    lines: list[str] = []
    if actions:
        lines.append("【你的操作】")
        for a in actions:
            lines.append(f"  · {a.detail}")
    if effects:
        lines.append("【造成的效果】")
        for e in effects:
            lines.append(f"  · {e}")

    # Situation tail for combat
    if str(after.get("state_type")) in ("monster", "elite", "boss"):
        foes = _enemy_lines(after)
        if foes:
            lines.append("【当前敌人】 " + "；".join(foes))

    return "\n".join(lines)


def append_action_log(text: str) -> None:
    if not text.strip():
        return
    from datetime import datetime

    from plugins.sts2.storage import action_log_path

    stamp = datetime.now(UTC).strftime("%H:%M:%S")
    try:
        with action_log_path().open("a", encoding="utf-8") as fh:
            fh.write(f"\n### {stamp} UTC\n{text.strip()}\n")
    except Exception:
        pass


def read_action_log_tail(*, max_chars: int = 6000) -> str:
    from plugins.sts2.storage import action_log_path

    path = action_log_path()
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    return text[-max_chars:] if text else ""
