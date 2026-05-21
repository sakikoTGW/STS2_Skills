"""Runtime data paths — Hermes, OpenClaw, or AstrBot (see ``platform_home``)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def sts2_home() -> Path:
    from plugins.sts2.config import load_sts2_config
    from plugins.sts2.platform_home import resolve_sts2_home

    path = resolve_sts2_home(
        config_log_dir=str(load_sts2_config().get("log_dir") or ""),
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def trajectories_dir() -> Path:
    path = sts2_home() / "trajectories"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_dir() -> Path:
    path = sts2_home() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def strategy_dir() -> Path:
    path = sts2_home() / "strategy"
    path.mkdir(parents=True, exist_ok=True)
    return path


def hot_notes_path() -> Path:
    return sts2_home() / "hot_notes.md"


def strategy_path() -> Path:
    return strategy_dir() / "strategy.yaml"


def live_feed_path() -> Path:
    return sts2_home() / "live_feed.md"


def action_log_path() -> Path:
    return sts2_home() / "action_log.md"


def new_trajectory_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return trajectories_dir() / f"run_{stamp}.jsonl"


def pending_question_path() -> Path:
    return sts2_home() / "pending_question.json"
