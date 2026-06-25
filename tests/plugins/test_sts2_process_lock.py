"""Cross-process driver lock safety."""

from __future__ import annotations

import os

from plugins.sts2 import driver_lock
from plugins.sts2.process_lock import clear_if_stale, foreign_holder_pid, try_acquire


def test_foreign_holder_blocks_manual_act(sts2_env, monkeypatch):
    lock = sts2_env / "sts2" / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("99999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.storage.sts2_home", lambda: sts2_env / "sts2")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == 99999,
    )

    blocked = driver_lock.manual_act_blocked()
    assert blocked is not None
    assert "99999" in blocked


def test_clear_if_stale_skips_live_foreign_holder(sts2_env, monkeypatch):
    lock = sts2_env / ".autoplay.lock"
    lock.write_text("42424\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == 42424,
    )

    assert foreign_holder_pid(lock) == 42424
    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_clear_if_stale_removes_dead_holder(sts2_env, monkeypatch):
    lock = sts2_env / ".autoplay.lock"
    lock.write_text("1\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)

    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_try_acquire_after_stale_clear(sts2_env, monkeypatch):
    lock = sts2_env / ".autoplay.lock"
    lock.write_text("1\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)

    clear_if_stale(lock)
    assert try_acquire(lock, label="test")
    try:
        assert foreign_holder_pid(lock) is None
        assert holder_pid_is_self(lock)
    finally:
        from plugins.sts2.process_lock import release

        release()


def holder_pid_is_self(lock):
    from plugins.sts2.process_lock import holder_pid

    return holder_pid(lock) == os.getpid()
