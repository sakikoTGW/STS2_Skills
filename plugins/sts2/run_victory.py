"""Full-run victory: Act1 → Act2 → Act3 (三幕通关), not stopping at Act1."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

_VICTORY_FILE = "FULL_RUN_CLEARED.txt"
_MILESTONE_PREFIX = "ACT{}_MILESTONE.txt"


def victory_file_name() -> str:
    return _VICTORY_FILE


def milestone_file_name(act_cleared: int) -> str:
    return _MILESTONE_PREFIX.format(act_cleared)


def run_act(state: dict | None) -> int:
    if not state:
        return 1
    run = state.get("run") or {}
    try:
        return max(1, int(run.get("act") or 1))
    except (TypeError, ValueError):
        return 1


def _state_blob(state: dict) -> str:
    screen = str(state.get("menu_screen") or "").lower()
    opts = json.dumps(state.get("options") or [], ensure_ascii=False).lower()
    return screen + " " + opts + " " + str(state.get("state_type") or "").lower()


def detect_full_run_victory(state: dict) -> bool:
    """True only when the entire run (三幕) is won — NOT Act1→Act2 transition."""
    if not isinstance(state, dict):
        return False
    act = run_act(state)
    # Past Act3
    if act >= 4:
        return True

    blob = _state_blob(state)
    st = str(state.get("state_type") or "").lower()

    # Act transition screens (must NOT count as full win)
    if act <= 2 and any(
        k in blob for k in ("act 2", "act2", "act 3", "act3", "下一幕", "depart", "ascend")
    ):
        return False

    if act < 3:
        return False

    run_win_keywords = (
        "run victory",
        "run complete",
        "campaign",
        "entire run",
        "you win",
        "victory",
        "triumph",
        "通关",
        "胜利",
        "complete",
    )
    if any(k in blob for k in run_win_keywords):
        return True

    if st == "game_over":
        player = state.get("player") or {}
        try:
            hp = int(player.get("hp", player.get("current_hp", 0)))
        except (TypeError, ValueError):
            hp = 0
        if hp > 0 and "defeat" not in blob and "death" not in blob:
            return True

    return False


def detect_act_milestone(
    state: dict, *, last_act: int
) -> Optional[Tuple[int, str]]:
    """If user just cleared act N (entered act N+1), return (N, message)."""
    if not isinstance(state, dict):
        return None
    act = run_act(state)
    if last_act < 2 and act >= 2:
        return (1, "★ 第一幕 (Act1) 已通过 — 继续打 Act2/Act3，不停止。")
    if last_act < 3 and act >= 3:
        return (2, "★ 第二幕 (Act2) 已通过 — 继续 Act3 Boss，不停止。")
    return None


def bootstrap_full_run_rules() -> None:
    from plugins.sts2.act1_clear import bootstrap_win_focus_rules
    from plugins.sts2.notes import merge_strategy_rules

    bootstrap_win_focus_rules()
    from plugins.sts2.ironclad_builds import bootstrap_build_rules

    bootstrap_build_rules()
    merge_strategy_rules(
        [
            "全剧目标：同一局打通 Act1→Act2→Act3，进下一幕不视为最终通关。",
            "Act2/3：HP>60% 且非连精英才进精英；每幕 Boss 前一层优先营火。",
            "Boss 战：先格挡再高伤；三幕全程禁止敌人回合 end_turn。",
            "战斗后奖励默认必拿牌；仅 Act1 第12层后且三张全是打击、牌组已有5+打击且界面有跳过钮时才可跳过。",
            "营火升级：优先升能力/核心技，少升打击；无优质目标可不升。",
            "选牌/升级前先看 Wiki 与局势，用理解+构筑判断，勿凭印象瞎拿。",
        ],
        source="bootstrap",
    )
