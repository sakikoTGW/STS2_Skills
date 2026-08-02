"""Cross-process driver lock safety."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest


def test_act_reports_api_error_as_failure(sts2_env, monkeypatch):
    from plugins.sts2.tools import handle_sts2_act

    monkeypatch.setattr(
        "plugins.sts2.client.get_singleplayer_state",
        lambda **kw: (200, {"state_type": "monster", "player": {"hp": 50}}),
    )
    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda body: (200, {"status": "error", "message": "Unknown action"}),
    )
    raw = handle_sts2_act({"action": "bogus_action"})
    data = json.loads(raw)
    assert data["success"] is False
    assert data.get("status") == "error"


def test_foreign_holder_pid_detects_other_process(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("99999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 99999)
    assert foreign_holder_pid(lock) == 99999


def test_foreign_holder_pid_ignores_self(sts2_env):
    from plugins.sts2.process_lock import foreign_holder_pid
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{os.getpid()}\nautoplay\n", encoding="utf-8")
    assert foreign_holder_pid(lock) is None


def test_clear_if_stale_skips_foreign_holder(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("42424\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 42424)
    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_manual_act_blocked_by_foreign_lock(sts2_env, monkeypatch):
    from plugins.sts2 import driver_lock
    from plugins.sts2.storage import sts2_home
    from plugins.sts2.tools import handle_sts2_act

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("88888\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 88888)
    monkeypatch.setattr("plugins.sts2.config.enforce_single_driver_enabled", lambda cfg=None: True)

    raw = handle_sts2_act({"action": "end_turn"})
    data = json.loads(raw)
    assert data.get("success") is False
    assert "88888" in str(data.get("error", ""))
    driver_lock.release("autoplay")
