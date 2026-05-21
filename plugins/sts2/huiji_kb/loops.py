"""Computable enemy behavior loops — match T+0, predict T+N, estimate damage."""

from __future__ import annotations

import re
from typing import Any

_ATTACK = frozenset({"attack", "multi_attack", "multicast", "damage"})


def _slug(name: str) -> str:
    s = re.sub(r"\s+", "_", str(name or "").strip())
    return s[:48] or "step"


def _norm_label(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "").strip().lower())


def enemy_strength(enemy: dict) -> int:
    for p in enemy.get("powers") or []:
        if not isinstance(p, dict):
            continue
        blob = " ".join(
            str(p.get(k) or "") for k in ("id", "name", "description")
        ).lower()
        if "strength" in blob or "力量" in blob:
            try:
                return int(p.get("amount") or p.get("stacks") or p.get("count") or 0)
            except (TypeError, ValueError):
                pass
    try:
        return int(enemy.get("strength") or enemy.get("str") or 0)
    except (TypeError, ValueError):
        return 0


def normalize_step(raw: dict[str, Any], *, idx: int = 0) -> dict[str, Any]:
    """Canonical loop step for damage / prediction."""
    name = str(raw.get("name") or raw.get("intent_key") or f"step_{idx}")
    typ = str(raw.get("type") or "other").lower()
    step: dict[str, Any] = {
        "key": str(raw.get("key") or _slug(name)),
        "name": name,
        "type": typ,
        "aliases": list(raw.get("aliases") or []),
    }
    for src, dst in (
        ("damage", "damage_base"),
        ("damage_base", "damage_base"),
        ("base_damage", "damage_base"),
    ):
        if raw.get(src) is not None:
            try:
                step["damage_base"] = int(raw[src])
            except (TypeError, ValueError):
                pass
            break
    if raw.get("hits") is not None:
        try:
            step["hits"] = max(1, int(raw["hits"]))
        except (TypeError, ValueError):
            step["hits"] = 1
    else:
        step["hits"] = 1
    if raw.get("block") is not None:
        try:
            step["block_gain"] = int(raw["block"])
        except (TypeError, ValueError):
            pass
    if raw.get("block_gain") is not None:
        step["block_gain"] = int(raw["block_gain"])
    if raw.get("effects"):
        step["effects"] = list(raw["effects"])
    elif raw.get("effect"):
        step["effects"] = [{"raw": str(raw["effect"])}]
        m = re.search(r"\+(\d+)\s*力量", str(raw["effect"]))
        if m:
            step["effects"] = [{"power": "strength", "delta": int(m.group(1))}]
    if raw.get("scales_strength") or typ == "attack" and step.get("damage_base"):
        step.setdefault("damage_per_strength", float(raw.get("damage_per_strength", 1)))
    if raw.get("formula"):
        step["formula"] = str(raw["formula"])
    if raw.get("notes"):
        step["notes"] = str(raw["notes"])
    return step


def build_cycle_from_intents(intents: list[dict[str, Any]]) -> dict[str, Any]:
    steps = [normalize_step(it, idx=i) for i, it in enumerate(intents) if it.get("name")]
    if not steps:
        return {}
    return {"kind": "cycle", "length": len(steps), "steps": steps}


def parse_loop_arrow_text(text: str, intent_names: list[str]) -> list[str]:
    """Parse '咆哮→咬→猛击' or 'A-B-C' order from wiki prose."""
    if not text:
        return []
    for sep in ("→", "->", "－>", "=>", "→", "—>"):
        if sep in text:
            parts = [p.strip() for p in text.split(sep) if p.strip()]
            if len(parts) >= 2:
                return parts
    m = re.search(r"循环[：:]?\s*([^。；]+)", text)
    if m:
        chunk = m.group(1)
        for sep in ("、", ",", "，", "然后", "再"):
            if sep in chunk:
                return [p.strip() for p in re.split(sep, chunk) if p.strip()]
        return [chunk.strip()] if chunk.strip() else []
    return []


def reorder_steps_by_names(
    steps: list[dict[str, Any]], order: list[str]
) -> list[dict[str, Any]]:
    if not order:
        return steps
    by_name = {_norm_label(s["name"]): s for s in steps}
    out: list[dict[str, Any]] = []
    used: set[str] = set()
    for nm in order:
        key = _norm_label(nm)
        if key in by_name:
            out.append(by_name[key])
            used.add(key)
    for s in steps:
        if _norm_label(s["name"]) not in used:
            out.append(s)
    return out


def attach_behavior_loop(entry: dict[str, Any]) -> dict[str, Any]:
    """Ensure entry has behavior_loop (from explicit, prose, or intents)."""
    if entry.get("behavior_loop"):
        bl = entry["behavior_loop"]
        if bl.get("steps"):
            bl["steps"] = [
                normalize_step(s, idx=i) if isinstance(s, dict) else s
                for i, s in enumerate(bl["steps"])
            ]
            bl["length"] = len(bl["steps"])
        entry["behavior_loop"] = bl
        return entry

    intents = entry.get("intents") or []
    order = parse_loop_arrow_text(str(entry.get("pattern") or ""), [])
    if not order:
        order = parse_loop_arrow_text(str(entry.get("description") or ""), [])

    steps = [normalize_step(it, idx=i) for i, it in enumerate(intents)]
    if order:
        steps = reorder_steps_by_names(steps, order)
    loop = build_cycle_from_intents(steps)
    if loop:
        entry["behavior_loop"] = loop
    return entry


def step_matches_intent(step: dict[str, Any], intent: dict) -> bool:
    label = _norm_label(
        str(intent.get("label") or intent.get("name") or intent.get("description") or "")
    )
    if not label:
        return False
    names = [_norm_label(step.get("name") or "")]
    names.extend(_norm_label(a) for a in step.get("aliases") or [])
    for nm in names:
        if not nm:
            continue
        if nm in label or label in nm:
            return True
        if len(nm) >= 2 and len(label) >= 2 and (nm[:2] in label or label[:2] in nm):
            return True
    typ = str(intent.get("type") or "").lower()
    styp = str(step.get("type") or "").lower()
    if typ in _ATTACK and styp == "attack" and not names[0]:
        return True
    if typ.startswith("debuff") and styp == "debuff":
        for nm in names:
            if nm and (nm in label or "debuff" in label or "shrink" in label):
                return True
        if "shrink" in label or "缩小" in label:
            return True
    return False


def match_cycle_index(loop: dict[str, Any], intent: dict | None) -> int:
    steps = loop.get("steps") or []
    if not steps:
        return 0
    if not intent:
        return 0
    for i, step in enumerate(steps):
        if step_matches_intent(step, intent):
            return i
    return 0


def predict_cycle_steps(
    loop: dict[str, Any],
    *,
    start_index: int = 0,
    count: int = 3,
) -> list[tuple[int, dict[str, Any]]]:
    """Return [(cycle_index, step), ...] for T+0..T+(count-1)."""
    steps = loop.get("steps") or []
    if not steps:
        return []
    n = len(steps)
    out: list[tuple[int, dict[str, Any]]] = []
    for off in range(count):
        idx = (start_index + off) % n
        out.append((idx, steps[idx]))
    return out


def apply_step_effects_to_virtual(
    step: dict[str, Any], virtual: dict[str, int]
) -> None:
    for eff in step.get("effects") or []:
        if not isinstance(eff, dict):
            continue
        if eff.get("power") == "strength" or "力量" in str(eff.get("raw") or ""):
            try:
                virtual["strength"] = virtual.get("strength", 0) + int(
                    eff.get("delta") or 0
                )
            except (TypeError, ValueError):
                pass


def _apply_damage_modifiers(
    dmg: int, loop: dict[str, Any] | None
) -> int:
    if dmg <= 0 or not loop:
        return dmg
    for mod in loop.get("modifiers") or []:
        if mod.get("type") == "damage_cap_per_turn":
            try:
                cap = int(mod.get("value") or 0)
                if cap > 0:
                    dmg = min(dmg, cap)
            except (TypeError, ValueError):
                pass
    return dmg


def estimate_step_damage(
    step: dict[str, Any],
    enemy: dict,
    *,
    context: dict[str, Any] | None = None,
    virtual_strength: int | None = None,
    loop: dict[str, Any] | None = None,
) -> int:
    """Total incoming damage this step (all hits)."""
    ctx = context or {}
    if str(step.get("type") or "").lower() not in ("attack",) and not step.get(
        "damage_base"
    ):
        return 0

    hits = int(step.get("hits") or 1)
    base = int(step.get("damage_base") or step.get("damage") or 0)
    per_str = float(step.get("damage_per_strength") or 0)
    if step.get("scales_strength"):
        per_str = float(step.get("damage_per_strength") or 1)
    str_val = (
        virtual_strength
        if virtual_strength is not None
        else enemy_strength(enemy)
    )

    formula = str(step.get("formula") or "")
    if formula == "nob_skull":
        skills = int(ctx.get("skills_played_this_turn") or 0)
        return (base + 2 * skills) * hits
    if formula == "nob_skull_conservative":
        return (base + 2 * max(2, int(ctx.get("skills_played_this_turn") or 2))) * hits

    dmg = max(0, int(base + per_str * str_val)) * hits
    return _apply_damage_modifiers(dmg, loop)


def forecast_enemy(
    kb_entry: dict[str, Any],
    enemy: dict,
    *,
    horizon: int = 3,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Computes cycle position + T+0..T+(horizon-1) damage estimates."""
    loop = kb_entry.get("behavior_loop") or {}
    intents = enemy.get("intents") or []
    it0 = intents[0] if intents and isinstance(intents[0], dict) else None

    if loop.get("kind") == "phases":
        return _forecast_phases(kb_entry, enemy, horizon=horizon, context=context)

    if not loop.get("steps"):
        return {"ok": False, "reason": "no_loop"}

    idx = match_cycle_index(loop, it0)
    virtual = {"strength": enemy_strength(enemy)}
    rows: list[dict[str, Any]] = []
    total_atk = 0

    for off, (cidx, step) in enumerate(
        predict_cycle_steps(loop, start_index=idx, count=horizon)
    ):
        dmg = estimate_step_damage(
            step,
            enemy,
            context=context,
            virtual_strength=virtual["strength"],
            loop=loop,
        )
        if str(step.get("type") or "").lower() == "attack" or dmg > 0:
            total_atk += dmg
        rows.append(
            {
                "offset": off,
                "cycle_index": cidx,
                "cycle_len": loop.get("length") or len(loop.get("steps") or []),
                "step": step,
                "damage_est": dmg,
                "strength_virtual": virtual["strength"],
            }
        )
        apply_step_effects_to_virtual(step, virtual)

    return {
        "ok": True,
        "start_index": idx,
        "cycle_length": loop.get("length") or len(loop.get("steps") or []),
        "horizon": rows,
        "total_attack_damage": total_atk,
        "matched_T0": bool(it0 and step_matches_intent(rows[0]["step"], it0)),
    }


def _forecast_phases(
    kb_entry: dict[str, Any],
    enemy: dict,
    *,
    horizon: int,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Lagavulin-style phased loops."""
    phases = (kb_entry.get("behavior_loop") or {}).get("phases") or []
    it0 = (enemy.get("intents") or [{}])[0] if enemy.get("intents") else {}
    label = str(it0.get("label") or it0.get("name") or "").lower()
    sleep = any(k in label for k in ("sleep", "入睡", "冥想", "stun"))
    phase_id = "sleep" if sleep else "awake"
    phase = next((p for p in phases if p.get("id") == phase_id), None)
    if not phase:
        phase = phases[-1] if phases else None
    if not phase:
        return {"ok": False, "reason": "no_phase"}
    sub = phase.get("loop") or phase
    fake_entry = {**kb_entry, "behavior_loop": sub}
    out = forecast_enemy(fake_entry, enemy, horizon=horizon, context=context)
    out["phase"] = phase_id
    return out


def format_loop_forecast(forecast: dict[str, Any]) -> str:
    if not forecast.get("ok"):
        return ""
    parts: list[str] = []
    phase = forecast.get("phase")
    if phase:
        parts.append(f"阶段={phase}")
    ci = forecast.get("start_index", 0)
    clen = forecast.get("cycle_length", 0)
    if clen:
        parts.append(f"循环位[{ci + 1}/{clen}]")
    for row in forecast.get("horizon") or []:
        off = row["offset"]
        step = row["step"]
        nm = step.get("name") or "?"
        dmg = row.get("damage_est", 0)
        tag = f"T+{off}:{nm}"
        if dmg > 0:
            tag += f"≈{dmg}伤"
        elif str(step.get("type")) == "buff":
            tag += "(增益)"
        elif str(step.get("type")) == "block":
            tag += f"(+{step.get('block_gain', '?')}防)"
        parts.append(tag)
    tot = forecast.get("total_attack_damage", 0)
    if tot > 0:
        parts.append(f"未来{len(forecast.get('horizon') or [])}拍攻击合计≈{tot}")
    return "行为循环|" + " ".join(parts)


def kb_predicted_slot(
    kb_entry: dict[str, Any],
    enemy: dict,
    offset: int,
    *,
    context: dict[str, Any] | None = None,
) -> tuple[str, str, int, int]:
    """Combat FSM slot: (type, label, damage, hits)."""
    loop = kb_entry.get("behavior_loop") or {}
    if not loop.get("steps") and loop.get("kind") != "phases":
        return ("predicted", f"T+{offset}:无循环数据", 0, 1)
    fc = forecast_enemy(kb_entry, enemy, horizon=offset + 1, context=context)
    rows = fc.get("horizon") or []
    if offset >= len(rows):
        return ("predicted", f"T+{offset}:?", 0, 1)
    row = rows[offset]
    step = row["step"]
    dmg = int(row.get("damage_est") or 0)
    hits = int(step.get("hits") or 1)
    typ = "attack" if dmg > 0 else str(step.get("type") or "other")
    label = f"T+{offset}:{step.get('name','?')}"
    if dmg:
        label += f"≈{dmg}"
    return (typ, label[:80], dmg, hits)
