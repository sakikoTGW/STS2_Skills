"""Dense reward signals from STS2 state transitions."""

from __future__ import annotations

from typing import Any


def _floor(run: Any) -> int:
    if not isinstance(run, dict):
        return 0
    try:
        return int(run.get("floor") or 0)
    except (TypeError, ValueError):
        return 0


def _hp(player: Any) -> int | None:
    if not isinstance(player, dict):
        return None
    try:
        return int(player.get("hp", player.get("current_hp")))
    except (TypeError, ValueError):
        return None


def compute_step_reward(
    prev: dict[str, Any] | None,
    nxt: dict[str, Any],
    *,
    act_ok: bool,
) -> float:
    reward = 0.0
    if not act_ok:
        reward -= 0.5

    prev_run = (prev or {}).get("run") if prev else None
    nxt_run = nxt.get("run")
    if _floor(nxt_run) > _floor(prev_run):
        reward += 0.3

    prev_hp = _hp((prev or {}).get("player"))
    nxt_hp = _hp(nxt.get("player"))
    if prev_hp is not None and nxt_hp is not None:
        reward += (nxt_hp - prev_hp) * 0.02

    st = str(nxt.get("state_type") or "")
    if st == "game_over":
        reward -= 2.0
    elif st == "rewards":
        reward += 0.1

    return round(reward, 4)
