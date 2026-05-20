"""Watch user play, ask when a turn/decision is unclear, save answers as style rules."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from plugins.sts2.combat_brain import decide_combat, incoming_attack_damage
from plugins.sts2.decision import _pick_map_node, _rule_action
from plugins.sts2.notes import append_hot_note, merge_strategy_rules
from plugins.sts2.storage import sts2_home
from plugins.sts2.visibility import describe_action, describe_delta, describe_situation

logger = logging.getLogger(__name__)

_COMBAT = frozenset({"monster", "elite", "boss"})
_DECISION_SCREENS = frozenset({
    "card_reward",
    "relic_select",
    "relic_select_boss",
    "event",
})


@dataclass
class CoachEvent:
    kind: str  # narrate | ask
    text: str
    meta: Dict[str, Any] = field(default_factory=dict)


def learn_log_path():
    p = sts2_home() / "learn_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log_learn(record: dict) -> None:
    try:
        with learn_log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("learn log: %s", exc)


def absorb_user_answer(question: str, answer: str, *, meta: Optional[dict] = None) -> dict:
    """Persist Q&A into hot_notes + strategy (called from autoplay provide_hint)."""
    answer = (answer or "").strip()
    if not answer:
        return {"saved": False, "error": "empty answer"}
    meta = meta or {}
    floor = meta.get("floor", "?")
    section = f"用户打法 第{floor}层"
    body = f"问：{question.strip()}\n答：{answer}"
    append_hot_note(section, body)
    rule = f"【用户偏好】{answer[:200]}"
    merge_strategy_rules([rule])
    _log_learn(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "answer": answer,
            "meta": meta,
        }
    )
    return {"saved": True, "rule": rule}


def _player_stats(state: dict) -> dict:
    p = state.get("player") or {}
    try:
        hp = int(p.get("hp", p.get("current_hp", 0)))
    except (TypeError, ValueError):
        hp = 0
    try:
        block = int(p.get("block", 0))
    except (TypeError, ValueError):
        block = 0
    try:
        energy = int(p.get("energy", 0))
    except (TypeError, ValueError):
        energy = 0
    return {"hp": hp, "block": block, "energy": energy}


def _enemy_hp_sum(state: dict) -> int:
    total = 0
    for e in (state.get("battle") or {}).get("enemies") or []:
        try:
            total += int(e.get("hp", 0))
        except (TypeError, ValueError):
            pass
    return total


def _floor(state: dict) -> int:
    try:
        return int((state.get("run") or {}).get("floor") or 0)
    except (TypeError, ValueError):
        return 0


class LearnCoach:
    """Stateful observer for one learn-mode session."""

    def __init__(self) -> None:
        self._turn_start: Optional[dict] = None
        self._prev_turn: Optional[str] = None
        self._pending_map: Optional[dict] = None
        self._pending_event: Optional[dict] = None
        self._asked_fingerprints: set[str] = set()

    def tick(self, prev: Optional[dict], curr: dict) -> List[CoachEvent]:
        events: List[CoachEvent] = []
        if not curr:
            return events

        st = str(curr.get("state_type") or "")
        battle = curr.get("battle") or {}
        turn = str(battle.get("turn") or "").lower()

        if prev:
            events.extend(self._check_combat_turn_end(prev, curr, turn))
            events.extend(self._check_map_choice(prev, curr))
            events.extend(self._check_decision_screen(prev, curr))

        if turn == "player" and self._prev_turn != "player":
            self._turn_start = curr

        if st in _DECISION_SCREENS and str((prev or {}).get("state_type")) != st:
            q = self._question_on_decision_screen(curr)
            if q:
                events.append(CoachEvent("ask", q, {"kind": "decision_screen", "state_type": st}))

        self._prev_turn = turn
        return events

    def _check_combat_turn_end(
        self, prev: dict, curr: dict, turn: str
    ) -> List[CoachEvent]:
        events: List[CoachEvent] = []
        pt = str((prev.get("battle") or {}).get("turn") or "").lower()
        if pt != "player" or turn != "enemy" or not self._turn_start:
            return events

        start = self._turn_start
        end = prev
        q = self._combat_turn_question(start, end)
        self._turn_start = None
        if q:
            fp = f"combat|{_floor(start)}|{q[:80]}"
            if fp not in self._asked_fingerprints:
                self._asked_fingerprints.add(fp)
                events.append(
                    CoachEvent(
                        "ask",
                        q,
                        {
                            "kind": "combat_turn",
                            "floor": _floor(start),
                            "state_type": start.get("state_type"),
                        },
                    )
                )
        else:
            delta = describe_delta(start, end)
            bot = decide_combat(start)
            _log_learn(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "kind": "combat_turn_ok",
                    "floor": _floor(start),
                    "delta": delta,
                    "bot_would": describe_action(start, bot),
                }
            )
        return events

    def _combat_turn_question(self, start: dict, end: dict) -> Optional[str]:
        reasons: List[str] = []
        p0 = _player_stats(start)
        p1 = _player_stats(end)
        enemies = (start.get("battle") or {}).get("enemies") or []
        incoming = incoming_attack_damage(enemies)
        hp_loss = max(0, p0["hp"] - p1["hp"])
        block_gain = max(0, p1["block"] - p0["block"])
        hp_dmg = max(0, _enemy_hp_sum(start) - _enemy_hp_sum(end))

        bot = decide_combat(start)
        bot_line = describe_action(start, bot)
        delta = describe_delta(start, end)

        if incoming >= 5 and block_gain < incoming // 2 and hp_loss > 0:
            reasons.append(
                f"敌人本回合约 {incoming} 伤害，你只加了 {block_gain} 格挡并掉了 {hp_loss} 血"
            )

        if incoming <= 2 and hp_dmg == 0 and p1["energy"] > 0:
            reasons.append(f"敌人威胁不大，但你没打出伤害且还剩 {p1['energy']} 能量就结束回合")

        if bot.get("action") == "play_card" and hp_dmg == 0 and p0["energy"] >= 2:
            card = _hand_card(start, bot.get("card_index"))
            if card and str(card.get("type", "")).lower() == "attack":
                reasons.append(
                    f"我本会出牌「{card.get('name', '?')}」，但这回合敌人血量没变"
                )

        if bot.get("action") == "play_card" and block_gain == 0 and incoming >= 4:
            card = _hand_card(start, bot.get("card_index"))
            cname = (card or {}).get("name", "格挡牌")
            if card and "defend" in str(card.get("id", "")).lower():
                reasons.append(f"我本会先打「{cname}」挡伤害，你这回合似乎没优先格挡")

        if not reasons:
            return None

        floor = _floor(start)
        sit = describe_situation(start)
        return (
            f"【学习·战斗回合结束 第{floor}层】\n"
            f"{sit}\n"
            f"你这回合变化：{delta or '(见上)'}\n"
            f"按我的规则会：{bot_line}\n"
            f"我不太理解：{'；'.join(reasons)}。\n"
            f"请用一句话说明你这回合的思路（回复后我会记入你的打法笔记）。"
        )

    def _check_map_choice(self, prev: dict, curr: dict) -> List[CoachEvent]:
        events: List[CoachEvent] = []
        if str(prev.get("state_type")) != "map":
            return events
        if str(curr.get("state_type")) == "map":
            return events

        opts = (prev.get("map") or {}).get("next_options") or prev.get("next_options") or []
        if len(opts) < 2:
            return events

        bot = _pick_map_node(opts, prev)
        bot_idx = bot.get("index")
        types = [str(o.get("type", "")).lower() for o in opts]
        if "elite" in types and bot_idx is not None:
            picked_elite = any(
                str(o.get("type", "")).lower() == "elite" and o.get("index") == bot_idx
                for o in opts
            )
            if not picked_elite:
                fp = f"map|{_floor(prev)}|elite"
                if fp in self._asked_fingerprints:
                    return events
                self._asked_fingerprints.add(fp)
                q = (
                    f"【学习·选路】第{_floor(prev)}层：地图有 {', '.join(types)}。\n"
                    f"我本会避开精英，你却选了别的路。\n"
                    f"为什么这回合这样选？（会记入打法笔记）"
                )
                events.append(
                    CoachEvent("ask", q, {"kind": "map", "floor": _floor(prev)})
                )
        return events

    def _check_decision_screen(self, prev: dict, curr: dict) -> List[CoachEvent]:
        events: List[CoachEvent] = []
        pst = str(prev.get("state_type") or "")
        cst = str(curr.get("state_type") or "")
        if pst in _DECISION_SCREENS and cst not in _DECISION_SCREENS:
            q = self._question_after_decision(prev, cst)
            if q:
                fp = f"dec|{pst}|{_floor(prev)}"
                if fp not in self._asked_fingerprints:
                    self._asked_fingerprints.add(fp)
                    events.append(
                        CoachEvent("ask", q, {"kind": "after_decision", "state_type": pst})
                    )
        return events

    def _question_on_decision_screen(self, state: dict) -> Optional[str]:
        st = str(state.get("state_type") or "")
        if st == "card_reward":
            cards = (state.get("card_reward") or {}).get("cards") or state.get("cards") or []
            if len(cards) >= 2:
                names = [str(c.get("name", "?")) for c in cards[:5]]
                return (
                    f"【学习·选牌】出现奖励：{', '.join(names)}。\n"
                    f"你打算选哪张、为什么？（选完也可再补充说明）"
                )
        if st == "event":
            ev = state.get("event") or {}
            opts = [o for o in (ev.get("options") or []) if not o.get("is_locked")]
            if len(opts) >= 2:
                titles = [str(o.get("title", "?")) for o in opts[:5]]
                return (
                    f"【学习·事件】{ev.get('event_name', '事件')}：\n"
                    f"选项：{' | '.join(titles)}\n"
                    f"你准备选哪个？理由是什么？"
                )
        if st in ("relic_select", "relic_select_boss"):
            relics = (state.get("relic_select") or {}).get("relics") or []
            if len(relics) >= 2:
                names = [str(r.get("name", "?")) for r in relics[:4]]
                return (
                    f"【学习·遗物】{' / '.join(names)} — 你更倾向哪个？为什么？"
                )
        return None

    def _question_after_decision(self, prev: dict, next_type: str) -> Optional[str]:
        st = str(prev.get("state_type") or "")
        ruled = _rule_action(prev)
        if not ruled:
            return None
        bot_line = describe_action(prev, ruled)
        return (
            f"【学习·{st}】你刚做完选择，界面进入 {next_type}。\n"
            f"若与我的默认不同：我本会 {bot_line}。\n"
            f"简要说说你的考量？（可跳过，直接继续打）"
        )


def _hand_card(state: dict, index: Any) -> Optional[dict]:
    try:
        want = int(index)
    except (TypeError, ValueError):
        return None
    for c in (state.get("player") or {}).get("hand") or []:
        if c.get("index") == want:
            return c
    return None
