"""Cross-process autoplay lock safety."""

from __future__ import annotations

import json
import os

import pytest


def test_foreign_holder_pid_detects_other_live_process(tmp_path, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("4242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(os, "getpid", lambda: 1111)

    assert foreign_holder_pid(lock) == 4242


def test_foreign_holder_pid_ignores_stale(tmp_path, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("4242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)
    monkeypatch.setattr(os, "getpid", lambda: 1111)

    assert foreign_holder_pid(lock) is None


def test_clear_if_stale_skips_live_foreign_holder(tmp_path, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("4242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(os, "getpid", lambda: 1111)

    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_clear_if_stale_removes_dead_holder(tmp_path, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("4242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)

    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_manual_act_blocked_when_foreign_lock(sts2_env, monkeypatch):
    from plugins.sts2 import driver_lock
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.write_text("9001\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 9001)

    blocked = driver_lock.manual_act_blocked()
    assert blocked is not None
    assert "9001" in blocked


def test_release_all_driver_locks_preserves_foreign_lock(sts2_env, monkeypatch):
    from plugins.sts2.manual_mode import release_all_driver_locks
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.write_text("9002\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 9002)

    release_all_driver_locks()
    assert lock.is_file()
    assert lock.read_text(encoding="utf-8").startswith("9002")


def test_act_reports_api_error_as_failure(sts2_env, monkeypatch):
    from plugins.sts2.tools import handle_sts2_act

    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda body: (200, {"status": "error", "message": "invalid card index"}),
    )
    raw = handle_sts2_act({"action": "play_card", "card_index": 99})
    data = json.loads(raw)
    assert data["success"] is False
    assert data["status"] == "error"
