"""Cross-process autoplay lock safety."""

from __future__ import annotations

import json
import os

import pytest


def test_foreign_holder_pid_detects_live_other(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid, try_acquire
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("99999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 99999)
    assert foreign_holder_pid(lock) == 99999


def test_foreign_holder_pid_ignores_self(sts2_env):
    from plugins.sts2.process_lock import foreign_holder_pid, try_acquire, release
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    assert try_acquire(lock, label="test")
    try:
        assert foreign_holder_pid(lock) is None
    finally:
        release()


def test_foreign_holder_pid_ignores_stale(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: False)
    assert foreign_holder_pid(lock) is None


def test_clear_if_stale_removes_dead_holder(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: False)
    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_clear_if_stale_keeps_live_foreign(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("99999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 99999)
    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_manual_act_blocked_by_foreign_lock(sts2_env, monkeypatch):
    from plugins.sts2 import driver_lock
    from plugins.sts2.storage import sts2_home
    from plugins.sts2.tools import handle_sts2_act

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("99999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 99999)

    raw = handle_sts2_act({"action": "end_turn"})
    data = json.loads(raw)
    assert data.get("success") is False
    assert "blocked" in str(data.get("error", "")).lower()
    assert driver_lock.active_mode() is None
