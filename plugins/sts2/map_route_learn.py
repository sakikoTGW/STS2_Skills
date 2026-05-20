"""Per-act map route learning — elite/?/rest choices tied to outcomes (not fixed HP rules)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plugins.sts2.storage import sts2_home

logger = logging.getLogger(__name__)

_ROUTE_LOG = "evolution/route_log.jsonl"
_STATS_FILE = "evolution/route_stats.json"
_PENDING: Optional[Dict[str, Any]] = None

_NODE_KINDS = ("elite", "boss", "rest", "shop", "monster", "event", "unknown")


def _enabled() -> bool:
    try:
        from plugins.sts2.manual_learn import _manual_learn_enabled

        return _manual_learn_enabled()
    except Exception:
        return False


def _log_path() -> Path:
    p = sts2_home() / _ROUTE_LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _stats_path() -> Path:
    p = sts2_home() / _STATS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _hp_ratio(state: dict) -> float:
    p = state.get("player") or {}
    try:
        hp = int(p.get("hp", p.get("current_hp", 1)))
        mx = int(p.get("max_hp", hp) or hp or 1)
        return round(hp / mx, 3) if mx > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def _floor(state: dict) -> int:
    run = state.get("run") or {}
    try:
        return int(run.get("floor") or run.get("floor_reached") or 0)
    except (TypeError, ValueError):
        return 0


def _act(state: dict) -> int:
    try:
        from plugins.sts2.run_victory import run_act

        return max(1, int(run_act(state)))
    except Exception:
        run = state.get("run") or {}
        try:
            return max(1, int(run.get("act") or 1))
        except (TypeError, ValueError):
            return 1


def _character(state: dict) -> str:
    run = state.get("run") or {}
    p = state.get("player") or {}
    for k in ("character", "class", "selected_character"):
        if run.get(k):
            return str(run[k]).upper()
        if p.get(k):
            return str(p[k]).upper()
    return "UNKNOWN"


def map_options(state: dict) -> List[dict]:
    m = state.get("map") if isinstance(state.get("map"), dict) else {}
    opts = m.get("next_options") or state.get("next_options") or []
    return [o for o in opts if isinstance(o, dict)]


def _node_kind(option: dict) -> str:
    label = " ".join(
        str(option.get(k) or "")
        for k in ("type", "symbol", "label", "room_type", "icon", "name", "title")
    ).lower()
    if "boss" in label:
        return "boss"
    if "elite" in label:
        return "elite"
    if "rest" in label or "campfire" in label:
        return "rest"
    if "shop" in label or "merchant" in label:
        return "shop"
    if "event" in label or "?" in label or "unknown" in label:
        return "event"
    if "monster" in label or "combat" in label or label.strip() == "m":
        return "monster"
    return "unknown"


def _option_label(option: dict) -> str:
    for k in ("type", "symbol", "label", "name", "title"):
        v = option.get(k)
        if v:
            return str(v)
    return _node_kind(option)


def _append_log(row: dict) -> None:
    try:
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("route log: %s", exc)


def _read_log(*, limit: int = 80) -> List[dict]:
    path = _log_path()
    if not path.is_file():
        return []
    rows: List[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows[-limit:]


def _load_stats() -> Dict[str, Any]:
    path = _stats_path()
    if not path.is_file():
        return {"version": 1, "by_act_char": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("by_act_char", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "by_act_char": {}}


def _save_stats(data: Dict[str, Any]) -> None:
    try:
        _stats_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("route stats save: %s", exc)


def _stats_key(act: int, char: str) -> str:
    return f"act{act}:{char}"


def _bump_stat(
    act: int,
    char: str,
    kind: str,
    *,
    picked: bool = False,
    combat_win: bool = False,
    death: bool = False,
    hp_before: float = 0.0,
    hp_after: float = 0.0,
) -> None:
    data = _load_stats()
    bucket = data["by_act_char"].setdefault(
        _stats_key(act, char),
        {"kinds": {}, "last_act_floor": 0},
    )
    kinds = bucket.setdefault("kinds", {})
    k = kinds.setdefault(
        kind,
        {
            "picked": 0,
            "wins": 0,
            "deaths_after": 0,
            "hp_before": [],
            "hp_after": [],
        },
    )
    if picked:
        k["picked"] = int(k.get("picked") or 0) + 1
        k.setdefault("hp_before", []).append(hp_before)
        k["hp_before"] = k["hp_before"][-40:]
    if combat_win:
        k["wins"] = int(k.get("wins") or 0) + 1
        k.setdefault("hp_after", []).append(hp_after)
        k["hp_after"] = k["hp_after"][-40:]
    if death:
        k["deaths_after"] = int(k.get("deaths_after") or 0) + 1
    _save_stats(data)


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    return s[len(s) // 2]


def stats_summary(act: int, char: str) -> List[str]:
    """Human lines from logged outcomes (your account, not generic guides)."""
    data = _load_stats()
    bucket = (data.get("by_act_char") or {}).get(_stats_key(act, char)) or {}
    kinds = bucket.get("kinds") or {}
    lines: List[str] = []
    for kind in _NODE_KINDS:
        k = kinds.get(kind)
        if not k or not k.get("picked"):
            continue
        picked = int(k.get("picked") or 0)
        wins = int(k.get("wins") or 0)
        deaths = int(k.get("deaths_after") or 0)
        hb = _median([float(x) for x in k.get("hp_before") or []])
        ha = _median([float(x) for x in k.get("hp_after") or []])
        extra = ""
        if hb is not None:
            extra += f" 选时HP≈{hb:.0%}"
        if ha is not None and wins:
            extra += f" 战后HP≈{ha:.0%}"
        lines.append(
            f"  · {kind}: 选过{picked}次，战后存活{wins}次，选后阵亡{deaths}次{extra}"
        )
    return lines


def record_map_pick(state: dict, body: dict) -> None:
    """Remember which node we chose while on map."""
    global _PENDING
    if not _enabled():
        return
    if str(body.get("action") or "") != "choose_map_node":
        return
    if str(state.get("state_type") or "") != "map":
        return
    opts = map_options(state)
    try:
        ix = int(body.get("index", -1))
    except (TypeError, ValueError):
        ix = -1
    opt = next((o for o in opts if o.get("index") == ix), opts[0] if opts else {})
    kind = _node_kind(opt)
    _PENDING = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "act": _act(state),
        "floor": _floor(state),
        "char": _character(state),
        "hp_before": _hp_ratio(state),
        "kind": kind,
        "label": _option_label(opt),
        "index": ix,
    }
    row = dict(_PENDING, event="map_pick")
    _append_log(row)


def _resolve_pending(
    outcome: str,
    nxt: dict,
    *,
    prev_type: str = "",
) -> None:
    global _PENDING
    if not _PENDING:
        return
    p = dict(_PENDING)
    p["outcome"] = outcome
    p["hp_after"] = _hp_ratio(nxt)
    p["after_screen"] = str(nxt.get("state_type") or "")
    p["event"] = "map_outcome"
    _append_log(p)

    act = int(p.get("act") or 1)
    char = str(p.get("char") or "UNKNOWN")
    kind = str(p.get("kind") or "unknown")
    hp_b = float(p.get("hp_before") or 0)
    hp_a = float(p.get("hp_after") or 0)

    if outcome == "combat_win":
        _bump_stat(act, char, kind, picked=True, combat_win=True, hp_before=hp_b, hp_after=hp_a)
    elif outcome in ("death", "game_over", "run_end"):
        _bump_stat(act, char, kind, picked=True, death=True, hp_before=hp_b, hp_after=hp_a)
    else:
        _bump_stat(act, char, kind, picked=True, hp_before=hp_b, hp_after=hp_a)

    _PENDING = None

    if outcome in ("combat_win", "death", "game_over") and kind == "elite":
        _maybe_reflect_route(p, nxt, outcome=outcome)


def _maybe_reflect_route(pick: dict, state: dict, *, outcome: str) -> None:
    from plugins.sts2.config import load_sts2_config

    if not load_sts2_config().get("manual_map_reflect", True):
        return
    act = int(pick.get("act") or 1)
    char = str(pick.get("char") or "?")
    lines = stats_summary(act, char)
    if not lines:
        return
    try:
        from plugins.sts2.llm_util import sts2_call_llm
        from plugins.sts2.run_objective import llm_map_route_system

        raw = sts2_call_llm(
            [
                {
                    "role": "system",
                    "content": (
                        "你是 STS2 地图路线分析师。目标：提高通关率、降低整局战损，"
                        "不是鼓励多打精英。"
                        + llm_map_route_system()
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"角色={char} Act{act} 刚结束一次「{pick.get('label')}」({pick.get('kind')})，"
                        f"结果={outcome}，选路时HP={pick.get('hp_before')}, 之后HP={pick.get('hp_after')}。\n"
                        f"本账号 Act{act} 累计统计:\n"
                        + "\n".join(lines)
                        + "\n\n写 1-2 条「候选：」路线规则（是否多打精英必须写清条件）。"
                    ),
                },
            ],
            max_tokens=380,
            temperature=0.25,
        )
    except Exception as exc:
        logger.debug("map route reflect: %s", exc)
        return

    rules = _extract_candidate_rules(raw)
    if not rules:
        return
    from plugins.sts2.evolution_loop import propose_rule_changes

    propose_rule_changes(rules, source="map_route")
    try:
        from plugins.sts2.manual_learn import _notify_reflection

        _notify_reflection(
            {
                "label": f"map_{pick.get('kind')}",
                "floor": pick.get("floor"),
                "summary": raw[:800],
                "reflected": True,
            }
        )
    except Exception:
        pass


def _extract_candidate_rules(text: str) -> List[str]:
    rules: List[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "候选：" in line or line.startswith("候选:"):
            body = re.split(r"候选[:：]", line, maxsplit=1)[-1].strip()
            if len(body) > 10:
                rules.append(body[:240])
        elif line.startswith(("-", "•")) and len(line) > 12:
            body = line.lstrip("-• ").strip()
            if "地图" in body or "精英" in body or "路线" in body or "Act" in body:
                rules.append(body[:240])
        if len(rules) >= 2:
            break
    return rules


def _reflect_act_transition(prev: dict, nxt: dict) -> None:
    pa, na = _act(prev), _act(nxt)
    if na <= pa:
        return
    char = _character(nxt)
    episodes = [
        r
        for r in _read_log(60)
        if int(r.get("act") or 0) == pa and str(r.get("char") or "").upper() == char
    ]
    if len(episodes) < 2:
        return
    picks = [e for e in episodes if e.get("event") == "map_pick"]
    outcomes = [e for e in episodes if e.get("event") == "map_outcome"]
    summary_lines = stats_summary(pa, char)
    try:
        from plugins.sts2.llm_util import sts2_call_llm
        from plugins.sts2.run_objective import llm_map_route_system

        raw = sts2_call_llm(
            [
                {
                    "role": "system",
                    "content": (
                        "总结一整幕地图路线规划。第一目的通关，第二目的控战损；"
                        "基于日志与统计，不要写死「前期必精英」。"
                        + llm_map_route_system()
                        + "输出 2-3 条「候选：」条件化路线原则。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{char} 完成 Act{pa}，进入 Act{na}。\n"
                        f"统计:\n" + "\n".join(summary_lines or ["(样本仍少)"])
                        + f"\n选路{len(picks)}次，有结果{len(outcomes)}次。\n"
                        + f"写本账号在 Act{pa} 的路线经验（精英/事件/营火权衡）。"
                    ),
                },
            ],
            max_tokens=500,
            temperature=0.28,
        )
    except Exception as exc:
        logger.debug("act map reflect: %s", exc)
        return
    rules = _extract_candidate_rules(raw)
    if rules:
        from plugins.sts2.evolution_loop import propose_rule_changes

        propose_rule_changes(rules, source="map_route_act")


def observe_transition(
    prev: Optional[dict],
    nxt: dict,
    *,
    action: Optional[dict] = None,
) -> Dict[str, Any]:
    """Hook from manual_learn.tick — map picks and outcomes."""
    out: Dict[str, Any] = {}
    if not _enabled() or not isinstance(nxt, dict):
        return out

    if action and str(prev.get("state_type") if prev else "") == "map":
        record_map_pick(prev or nxt, action)

    if not prev:
        return out

    pt = str(prev.get("state_type") or "")
    nt = str(nxt.get("state_type") or "")

    if pt == "map" and action and str(action.get("action") or "") == "choose_map_node":
        record_map_pick(prev, action)

    # Entered combat after map pick
    if pt == "map" and nt in ("monster", "elite", "boss"):
        pass  # pending kept until rewards/death

    if pt in ("monster", "elite", "boss") and nt == "rewards":
        _resolve_pending("combat_win", nxt, prev_type=pt)

    if nt in ("game_over",) or _hp_ratio(nxt) <= 0:
        _resolve_pending("death", nxt, prev_type=pt)

    if pt not in ("menu", "") and nt == "menu" and _floor(prev) > 0:
        _resolve_pending("run_end", nxt, prev_type=pt)

    if _act(nxt) > _act(prev):
        _reflect_act_transition(prev, nxt)
        out["act_route_reflect"] = True

    return out


def _option_run_hint(kind: str, hp: float) -> str:
    """Short run-level hint per node type (not single-node greed)."""
    if kind == "elite":
        if hp < 0.45:
            return " → 低血慎选：战后 HP 须够撑后续路径"
        if hp >= 0.7:
            return " → 血线够时可评估遗物换强度（看统计）"
        return " → 权衡遗物收益 vs 战后掉血"
    if kind == "rest":
        if hp < 0.85:
            return " → 控战损优先：回血/升级通常优于再赌精英"
        return " → 满血可跳过，除非下段缺营火"
    if kind in ("event", "unknown"):
        return " → ? 波动大；低血时权重低于营火"
    if kind == "shop":
        return " → 买药水/删牌服务通关，非消费贪"
    if kind == "monster":
        return " → 稳定掉血少于精英；缺强度时再考虑精英"
    if kind == "boss":
        return " → Boss 战：战前尽量营火/满药"
    return ""


def format_map_route_brief(state: dict) -> str:
    """Route planning block on map screen — run objective + stats + options."""
    if str(state.get("state_type") or "") != "map":
        return ""

    act = _act(state)
    char = _character(state)
    floor = _floor(state)
    hp = _hp_ratio(state)
    opts = map_options(state)

    try:
        from plugins.sts2.run_objective import format_map_run_objective_block

        objective = format_map_run_objective_block(state, opts)
    except Exception:
        objective = ""

    lines: List[str] = []
    if objective:
        lines.append(objective)
        lines.append("")
    lines.append(f"【路线规划】Act{act} 第{floor}层 · {char} · HP{hp:.0%}")

    adopted = route_rules_for_prompt(act=act)
    if adopted:
        lines.append("已采纳路线规则（须结合当前 HP 覆盖泛化）:")
        for r in adopted:
            lines.append(f"  · {r[:200]}")

    summ = stats_summary(act, char)
    if summ:
        lines.append(f"本账号 Act{act} 选路统计（战后存活/选后阵亡）:")
        lines.extend(summ)
    else:
        lines.append("(尚无本账号路线样本 — 选路会被记录，换幕后归纳「何时精英划算」)")

    lines.append("当前可选（index · 类型 · 标签 · 整局向提示）:")
    for o in opts[:10]:
        k = _node_kind(o)
        hint = _option_run_hint(k, hp)
        lines.append(
            f"  index={o.get('index')} · {k} · {_option_label(o)}{hint}"
        )

    lines.append(
        "纪律：一次只选一个 index；选路服务通关+控战损，勿为「多打精英」透支 Boss 前 HP。"
    )
    lines.append(
        '→ sts2_act {"action":"choose_map_node","index":<上表>}'
    )
    return "\n".join(lines)


def route_rules_for_prompt(*, act: int | None = None) -> List[str]:
    """Active strategy rules tagged map-related."""
    try:
        from plugins.sts2.evolution_loop import ranked_rules_for_prompt

        rules = ranked_rules_for_prompt(limit=20)
    except Exception:
        from plugins.sts2.notes import read_strategy

        rules = [str(r) for r in (read_strategy().get("rules") or [])]
    out: List[str] = []
    for r in rules:
        low = r.lower()
        if any(
            k in r or k in low
            for k in (
                "地图",
                "路线",
                "精英",
                "elite",
                "营火",
                "Act",
                "幕",
                "节点",
                "绕路",
            )
        ):
            out.append(r)
    return out[:6]
