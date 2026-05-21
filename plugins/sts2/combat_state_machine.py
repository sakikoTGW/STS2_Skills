"""Combat zone state machine — player / enemies / hand / discard / exhaust.

When any zone changes during player phase, optionally invoke combat LLM think.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from plugins.sts2.combat_brain import combat_should_wait

logger = logging.getLogger(__name__)


def _is_player_phase(state: dict) -> bool:
    battle = state.get("battle") or {}
    turn = str(battle.get("turn") or "").lower()
    if turn in ("player", "play", "your_turn"):
        if battle.get("is_play_phase") is False:
            return False
        return True
    if turn == "enemy":
        return False
    return not combat_should_wait(state)

_COMBAT = frozenset({"monster", "elite", "boss", "hand_select"})
_ZONES = ("player", "enemies", "hand", "discard", "exhaust")

_machine: Optional["CombatStateMachine"] = None


def get_combat_fsm() -> "CombatStateMachine":
    global _machine
    if _machine is None:
        _machine = CombatStateMachine()
    return _machine


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _powers_tuple(powers: Any) -> Tuple[Tuple[str, int], ...]:
    out: List[Tuple[str, int]] = []
    for p in powers or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or p.get("id") or "?")
        amt = _int(p.get("amount", p.get("stacks", p.get("count", 0))))
        out.append((name, amt))
    return tuple(sorted(out))


def _relics_tuple(relics: Any) -> Tuple[str, ...]:
    names: List[str] = []
    for r in relics or []:
        if isinstance(r, dict):
            names.append(str(r.get("name") or r.get("id") or "?"))
        elif r:
            names.append(str(r))
    return tuple(sorted(names))


def _intent_slot(it: dict) -> Tuple[str, str, int, int]:
    from plugins.sts2.combat_brain import _parse_intent_damage

    typ = str(it.get("type") or "")
    label = str(it.get("label") or it.get("description") or "")[:80]
    dmg = _parse_intent_damage(it)
    hits = _int(it.get("hits") or it.get("count") or 1, 1)
    return (typ, label, dmg, hits)


def _kb_slot_for_enemy(e: dict, offset: int) -> Optional[Tuple[str, str, int, int]]:
    try:
        from plugins.sts2.huiji_kb.loops import kb_predicted_slot
        from plugins.sts2.huiji_kb.store import lookup_enemy
        from plugins.sts2.wiki_enemy import normalize_enemy_wiki_id

        wid = normalize_enemy_wiki_id(e)
        kb = lookup_enemy(wid) if wid else None
        if kb and (kb.get("behavior_loop") or {}).get("steps"):
            return kb_predicted_slot(kb, e, offset)
    except Exception:
        pass
    return None


def _predicted_slot(key: str, offset: int, enemy: Optional[dict] = None) -> Tuple[str, str, int, int]:
    """Fill T+1/T+2 from KB behavior loop, else intent history heuristic."""
    if enemy and offset >= 1:
        slot = _kb_slot_for_enemy(enemy, offset)
        if slot:
            return slot
    try:
        from plugins.sts2.combat_turn_plan import predict_next_turn

        pred, note = predict_next_turn(key)
        for _ in range(1, offset):
            if pred == "likely_attack":
                pred, note = "likely_non_attack", "再下回合: 常休息/防/Buff"
            elif pred == "likely_non_attack":
                pred, note = "likely_attack", "再下回合: 常攻击"
            else:
                pred, note = "unknown", "样本不足"
        if pred == "likely_attack":
            return ("predicted", f"T+{offset}:推测攻击", 0, 1)
        if pred == "likely_non_attack":
            return ("predicted", f"T+{offset}:推测休息/防", 0, 1)
        return ("predicted", f"T+{offset}:{(note or '未知')[:36]}", 0, 1)
    except Exception:
        return ("predicted", f"T+{offset}:样本不足", 0, 1)


def _enemy_intents_three(e: dict) -> Tuple[Tuple[str, str, int, int], ...]:
    """Up to 3 intent slots: API multi-intent + predicted fill."""
    raw = [x for x in (e.get("intents") or []) if isinstance(x, dict)][:3]
    slots: List[Tuple[str, str, int, int]] = [_intent_slot(it) for it in raw]
    key = str(e.get("entity_id") or e.get("id") or e.get("name") or "?")
    off = 0
    while len(slots) < 3:
        if off == 0 and raw:
            off = 1
            continue
        kb_slot = _kb_slot_for_enemy(e, off)
        if kb_slot:
            slots.append(kb_slot)
        else:
            slots.append(_predicted_slot(key, off, enemy=e))
        off += 1
    return tuple(slots[:3])


def snapshot_player(state: dict) -> Tuple[Any, ...]:
    p = state.get("player") or {}
    return (
        _int(p.get("hp", p.get("current_hp", 0))),
        _int(p.get("max_hp", 0)),
        _int(p.get("block", 0)),
        _int(p.get("energy", 0)),
        _int(p.get("strength", p.get("str", 0))),
        _int(p.get("dexterity", p.get("dex", 0))),
        _powers_tuple(p.get("powers") or p.get("status")),
        _relics_tuple(p.get("relics")),
        tuple(
            (
                _int(pot.get("slot"), i),
                str(pot.get("id") or pot.get("name") or ""),
            )
            for i, pot in enumerate(p.get("potions") or [])
            if isinstance(pot, dict)
        ),
    )


def snapshot_enemies(state: dict) -> Tuple[Any, ...]:
    rows: List[Tuple[Any, ...]] = []
    for e in (state.get("battle") or {}).get("enemies") or []:
        if not isinstance(e, dict):
            continue
        mech = ""
        for k in ("mechanics", "mechanic", "traits", "keywords", "special"):
            v = e.get(k)
            if v:
                mech = json.dumps(v, ensure_ascii=False, sort_keys=True)[:200]
                break
        rows.append(
            (
                str(e.get("entity_id") or e.get("id") or "?"),
                str(e.get("name") or ""),
                _int(e.get("hp")),
                _int(e.get("max_hp")),
                _int(e.get("block")),
                _powers_tuple(e.get("powers")),
                _enemy_intents_three(e),
                mech,
                str(e.get("facing") or e.get("orientation") or ""),
            )
        )
    return tuple(sorted(rows))


def _pile_cards(pile: Any) -> Tuple[Tuple[str, str, int], ...]:
    out: List[Tuple[str, str, int]] = []
    for c in pile or []:
        if not isinstance(c, dict):
            continue
        out.append(
            (
                str(c.get("id") or ""),
                str(c.get("name") or "?"),
                _int(c.get("index"), -1),
            )
        )
    return tuple(out)


def snapshot_hand(state: dict) -> Tuple[Any, ...]:
    return _pile_cards((state.get("player") or {}).get("hand"))


def snapshot_discard(state: dict) -> Tuple[Any, ...]:
    p = state.get("player") or {}
    return _pile_cards(p.get("discard_pile") or p.get("discard"))


def snapshot_exhaust(state: dict) -> Tuple[Any, ...]:
    p = state.get("player") or {}
    return _pile_cards(p.get("exhaust_pile") or p.get("exhaust"))


_ZONE_SNAPSHOTTERS = {
    "player": snapshot_player,
    "enemies": snapshot_enemies,
    "hand": snapshot_hand,
    "discard": snapshot_discard,
    "exhaust": snapshot_exhaust,
}

_ZONE_LABELS = {
    "player": "我方(血/能量/Buff/遗物)",
    "enemies": "敌方(血/状态/机制/三回合意图)",
    "hand": "手牌区",
    "discard": "弃牌堆",
    "exhaust": "消耗堆",
}


def _battle_key(state: dict) -> str:
    run = state.get("run") or {}
    foes = (state.get("battle") or {}).get("enemies") or []
    ids = sorted(str(e.get("entity_id") or e.get("id") or "") for e in foes if isinstance(e, dict))
    return f"f{run.get('floor')}|{','.join(ids)}"


def _format_player_snap(t: Tuple[Any, ...]) -> List[str]:
    hp, mx, blk, en, strn, dex, pows, rels, pots = t
    lines = [
        f"HP {hp}/{mx} | 格挡{blk} | 能量{en}",
    ]
    if strn or dex:
        lines.append(f"  力{strn} 敏{dex}")
    if pows:
        lines.append("  Buff: " + ", ".join(f"{n}×{a}" for n, a in pows))
    if rels:
        lines.append("  遗物: " + ", ".join(rels[:10]))
    if pots:
        lines.append("  药水槽: " + ", ".join(f"{s}:{n}" for s, n in pots if n))
    return lines


def _format_intent_slot(slot: Tuple[str, str, int, int], turn_label: str) -> str:
    typ, label, dmg, hits = slot
    hit_s = f"×{hits}" if hits > 1 else ""
    dmg_s = f" 伤{dmg}" if dmg else ""
    return f"    {turn_label}: {typ}/{label}{dmg_s}{hit_s}"


def _format_enemies_snap(t: Tuple[Any, ...]) -> List[str]:
    lines: List[str] = []
    for row in t:
        eid, name, hp, mx, blk, pows, intents3, mech, facing = row
        lines.append(f"  {name}({eid}) HP{hp}/{mx} 格挡{blk}" + (f" 朝向{facing}" if facing else ""))
        if pows:
            lines.append("    能力: " + ", ".join(f"{n}×{a}" for n, a in pows))
        if mech:
            lines.append(f"    机制: {mech[:120]}")
        for i, slot in enumerate(intents3):
            lines.append(_format_intent_slot(slot, f"T+{i}"))
    return lines


def _format_pile_snap(label: str, cards: Tuple[Tuple[str, str, int], ...], *, tail: int = 12) -> List[str]:
    if not cards:
        return [f"  ({label}空)"]
    show = cards[-tail:] if len(cards) > tail else cards
    names = [f"{n}({i})" for _, n, i in show]
    extra = f" …共{len(cards)}张" if len(cards) > len(show) else ""
    return [f"  {label}: " + ", ".join(names) + extra]


def format_zone_snapshots(state: dict, snaps: Dict[str, Tuple[Any, ...]]) -> str:
    lines = ["【战斗状态机·五区快照】"]
    if "player" in snaps:
        lines.append("▸ 我方")
        lines.extend(_format_player_snap(snaps["player"]))
    if "enemies" in snaps:
        lines.append("▸ 敌方")
        lines.extend(_format_enemies_snap(snaps["enemies"]))
    if "hand" in snaps:
        lines.append("▸ 手牌")
        lines.extend(_format_pile_snap("手牌", snaps["hand"]))
    if "discard" in snaps:
        lines.append("▸ 弃牌堆(近尾)")
        lines.extend(_format_pile_snap("弃牌", snaps["discard"]))
    if "exhaust" in snaps:
        lines.append("▸ 消耗堆(近尾)")
        lines.extend(_format_pile_snap("消耗", snaps["exhaust"]))
    return "\n".join(lines)


def _diff_player(a: Tuple, b: Tuple) -> str:
    labels = ("HP", "maxHP", "格挡", "能量", "力量", "敏捷", "Buff", "遗物", "药水")
    bits = []
    for i, lab in enumerate(labels):
        if a[i] != b[i]:
            bits.append(f"{lab}: {a[i]} → {b[i]}")
    return "；".join(bits) if bits else "无变化"


def _diff_pile(a: Tuple, b: Tuple, name: str) -> str:
    if a == b:
        return ""
    return f"{name}: {len(a)}张 → {len(b)}张"


def zone_delta_text(zone: str, prev: Tuple[Any, ...], cur: Tuple[Any, ...]) -> str:
    if prev == cur:
        return ""
    if zone == "player":
        return _diff_player(prev, cur)
    if zone == "enemies":
        return "敌方状态/意图变化"
    if zone in ("hand", "discard", "exhaust"):
        return _diff_pile(prev, cur, _ZONE_LABELS[zone])
    return f"{zone}变化"


class CombatStateMachine:
    """Tracks five combat zones; fires LLM think on any zone change."""

    def __init__(self) -> None:
        self._battle_key = ""
        self._zones: Dict[str, Tuple[Any, ...]] = {}
        self._last_think_ts = 0.0
        self._last_think_fp = ""

    def reset(self) -> None:
        self._battle_key = ""
        self._zones.clear()
        self._last_think_fp = ""
        self._last_think_ts = 0.0

    def _in_combat(self, state: dict) -> bool:
        return str(state.get("state_type") or "") in _COMBAT

    def tick(self, state: dict) -> Dict[str, Any]:
        """Update FSM; return metadata for sts2_get_state / play_brief."""
        from plugins.sts2.config import load_sts2_config

        cfg = load_sts2_config()
        if not cfg.get("combat_fsm_enabled", True):
            return {"enabled": False}

        if not self._in_combat(state):
            if self._zones:
                self.reset()
                try:
                    from plugins.sts2.combat_turn_plan import reset_combat_session

                    reset_combat_session()
                except Exception:
                    pass
            return {"enabled": True, "in_combat": False}

        bk = _battle_key(state)
        if bk != self._battle_key:
            self.reset()
            self._battle_key = bk
            try:
                from plugins.sts2.combat_turn_plan import reset_combat_session

                reset_combat_session()
            except Exception:
                pass

        try:
            from plugins.sts2.combat_turn_plan import update_from_state

            update_from_state(state)
        except Exception:
            pass

        cur_snaps: Dict[str, Tuple[Any, ...]] = {
            z: _ZONE_SNAPSHOTTERS[z](state) for z in _ZONES
        }
        changed: List[str] = []
        deltas: Dict[str, str] = {}
        first_frame = not self._zones

        for z in _ZONES:
            prev = self._zones.get(z)
            cur = cur_snaps[z]
            if prev is None:
                changed.append(z)
                deltas[z] = "初始" if first_frame else "新出现"
            elif prev != cur:
                changed.append(z)
                deltas[z] = zone_delta_text(z, prev, cur) or "已更新"
            self._zones[z] = cur

        combined_fp = hashlib.sha256(
            json.dumps(cur_snaps, default=str).encode("utf-8")
        ).hexdigest()[:16]

        player_turn = _is_player_phase(state)
        think_required = bool(changed) and player_turn
        try:
            from plugins.sts2.manual_mode import manual_mode_enabled
            from plugins.sts2.play_mode import agent_play_mode

            if manual_mode_enabled() and not agent_play_mode():
                think_required = False
        except Exception:
            pass

        out: Dict[str, Any] = {
            "enabled": True,
            "in_combat": True,
            "battle_key": bk,
            "changed": bool(changed),
            "changed_zones": changed,
            "zone_deltas": deltas,
            "think_required": think_required,
            "player_turn": player_turn,
            "fingerprint": combined_fp,
            "snapshot_text": format_zone_snapshots(state, cur_snaps),
            "first_frame": first_frame and bool(changed),
        }

        manual = False
        agent_only = False
        try:
            from plugins.sts2.manual_mode import manual_mode_enabled
            from plugins.sts2.play_mode import agent_play_mode

            manual = manual_mode_enabled()
            agent_only = agent_play_mode()
        except Exception:
            pass
        if (
            think_required
            and cfg.get("combat_fsm_auto_think", True)
            and not manual
            and not agent_only
        ):
            think = self._maybe_run_think(state, cfg, combined_fp, changed, deltas)
            if think:
                out["think"] = think
                out["think_ran"] = not think.get("skipped")
        elif think_required and agent_only and cfg.get("mount_fsm_deep_think", True):
            try:
                from plugins.sts2.play_mode import mount_mode

                if mount_mode():
                    think = self._maybe_run_mount_think(
                        state, cfg, combined_fp, changed, deltas
                    )
                    if think:
                        out["think"] = think
                        out["think_ran"] = not think.get("skipped")
                else:
                    out["think_ran"] = False
            except Exception:
                out["think_ran"] = False
        else:
            out["think_ran"] = False

        return out

    def _maybe_run_mount_think(
        self,
        state: dict,
        cfg: dict,
        fp: str,
        changed: List[str],
        deltas: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        from plugins.sts2.play_mode import llm_play_enabled

        if not llm_play_enabled():
            return {"skipped": True, "reason": "HERMES_STS2_LLM_PLAY=0"}
        if fp == self._last_think_fp:
            return {"skipped": True, "reason": "same_fingerprint_as_last_think"}

        min_iv = float(cfg.get("combat_fsm_think_min_interval", 0.85))
        now = time.monotonic()
        if now - self._last_think_ts < min_iv:
            return {"skipped": True, "reason": "debounce_interval"}

        self._last_think_ts = now
        self._last_think_fp = fp

        zone_note = "；".join(
            f"{_ZONE_LABELS.get(z, z)}: {deltas.get(z, '变')}" for z in changed
        )
        try:
            from plugins.sts2.mount_combat_think import run_mount_deep_think

            return run_mount_deep_think(
                state,
                zone_note=zone_note,
                changed_zones=changed,
                memory_prefix=_fsm_memory_prefix(zone_note, changed),
            )
        except Exception as exc:
            logger.warning("mount_fsm think failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def _maybe_run_think(
        self,
        state: dict,
        cfg: dict,
        fp: str,
        changed: List[str],
        deltas: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        from plugins.sts2.play_mode import llm_play_enabled

        if not llm_play_enabled():
            return {
                "skipped": True,
                "reason": "HERMES_STS2_LLM_PLAY=0",
            }
        if fp == self._last_think_fp:
            return {"skipped": True, "reason": "same_fingerprint_as_last_think"}

        min_iv = float(cfg.get("combat_fsm_think_min_interval", 0.85))
        now = time.monotonic()
        if now - self._last_think_ts < min_iv:
            return {"skipped": True, "reason": "debounce_interval"}

        if not cfg.get("study_combat_play_llm", True):
            return {"skipped": True, "reason": "study_combat_play_llm=false"}

        self._last_think_ts = now
        self._last_think_fp = fp

        zone_note = "；".join(
            f"{_ZONE_LABELS.get(z, z)}: {deltas.get(z, '变')}" for z in changed
        )
        try:
            from plugins.sts2.combat_play_brain import decide_combat_play

            commentary, body, ok = decide_combat_play(
                state,
                memory=_fsm_memory_prefix(zone_note, changed),
            )
            return {
                "ok": ok,
                "trigger": "zone_change",
                "changed_zones": changed,
                "commentary": commentary,
                "suggested_action": body,
            }
        except Exception as exc:
            logger.warning("combat_fsm think failed: %s", exc)
            return {"ok": False, "error": str(exc)}


def _fsm_memory_prefix(zone_note: str, changed: List[str]) -> str:
    from plugins.sts2.run_objective import fsm_memory_run_hint

    return (
        f"{fsm_memory_run_hint()}\n"
        f"[状态机] 以下区域相对上次 get_state 发生变化: {', '.join(changed)}。\n"
        f"{zone_note}\n"
        "请基于五区快照做局内多回合最优（通关+控战损）；本玩家回合内用尽能量，"
        "每次 sts2_act 仍只发一张牌后 get_state 再续打。"
    )


def attach_combat_fsm(state: dict) -> Dict[str, Any]:
    """Run FSM tick; return combat_fsm dict (mutates play_brief if present)."""
    meta = get_combat_fsm().tick(state)
    if not meta.get("enabled") or not meta.get("in_combat"):
        return meta

    snap = meta.get("snapshot_text") or ""
    think = meta.get("think") or {}
    blocks: List[str] = [snap]
    if meta.get("think_required"):
        zones = ", ".join(_ZONE_LABELS.get(z, z) for z in meta.get("changed_zones") or [])
        blocks.append(f"【状态机】{zones} 已变化 → 须重新思考出牌")
    if think.get("commentary"):
        try:
            from plugins.sts2.manual_mode import manual_mode_enabled

            manual = manual_mode_enabled()
        except Exception:
            manual = False
        try:
            from plugins.sts2.play_mode import agent_play_mode

            agent_only = agent_play_mode()
        except Exception:
            agent_only = False
        try:
            from plugins.sts2.play_mode import mount_mode

            is_mount = mount_mode()
        except Exception:
            is_mount = False
        if is_mount:
            from plugins.sts2.decision_context import thinking_checklist

            tc = thinking_checklist(state)
            if tc:
                blocks.append(tc)
            if meta.get("think_required"):
                blocks.append(
                    "【挂载·状态机】五区有变 → 聊天须写深度思考（意图/算数/循环/本动/取舍/构筑），"
                    "再 sts2_act；勿照抄辅脑建议。"
                )
            if think.get("commentary"):
                sug = think.get("suggested_action") or {}
                blocks.append(
                    "【辅脑·深度参考·勿自动执行】\n"
                    + str(think.get("commentary", ""))[:4000]
                    + "\n参考动作: "
                    + json.dumps(sug, ensure_ascii=False)
                )
            elif think.get("skipped"):
                blocks.append(f"【辅脑】未生成: {think.get('reason', '')}")
        elif manual or agent_only:
            if think.get("commentary"):
                blocks.append(
                    "【状态机·历史参考·勿照抄】"
                    + str(think.get("commentary", ""))[:200]
                )
        else:
            blocks.append(
                "【状态机·LLM出牌建议】\n"
                + str(think.get("commentary", ""))
                + "\n建议动作: "
                + json.dumps(think.get("suggested_action") or {}, ensure_ascii=False)
            )
    elif think.get("skipped"):
        blocks.append(f"【状态机·LLM】未调用: {think.get('reason', '')}")

    fsm_block = "\n\n".join(blocks)
    meta["brief_block"] = fsm_block

    pb = state.get("play_brief")
    if isinstance(pb, str):
        if fsm_block not in pb:
            state["play_brief"] = fsm_block + "\n\n" + pb
    return meta
