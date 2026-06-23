"""Cross-process autoplay lock helpers."""

from __future__ import annotations

import os
from pathlib import Path

from plugins.sts2 import driver_lock
from plugins.sts2.process_lock import clear_if_stale, foreign_holder_pid, try_acquire


def test_foreign_holder_blocks_manual_act(sts2_env, monkeypatch):
    from plugins.sts2.storage import sts2_home
    from plugins.sts2.tools import handle_sts2_act

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 999999)

    raw = handle_sts2_act({"action": "end_turn"})
    data = __import__("json").loads(raw)
    assert data.get("success") is False
    assert "blocked" in str(data.get("error", raw)).lower()
    assert "999999" in str(data.get("error", raw))


def test_clear_if_stale_keeps_live_foreign_lock(sts2_env, monkeypatch):
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 424242)

    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_clear_if_stale_removes_dead_holder(sts2_env, monkeypatch):
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("1\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: False)

    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_foreign_holder_pid_ignores_self(sts2_env):
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    assert try_acquire(lock, label="test")
    try:
        assert foreign_holder_pid(lock) is None
    finally:
        driver_lock.release("autoplay")
        from plugins.sts2.process_lock import release

        release()


def test_release_all_driver_locks_does_not_steal_live_foreign(sts2_env, monkeypatch):
    from plugins.sts2.manual_mode import release_all_driver_locks
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("777777\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 777777)

    release_all_driver_locks()
    assert lock.is_file()
    assert foreign_holder_pid(lock) == 777777
