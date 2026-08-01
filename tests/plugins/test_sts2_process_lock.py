"""Cross-process lock safety for single-driver enforcement."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def lock_path(tmp_path) -> Path:
    path = tmp_path / "sts2home" / ".autoplay.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_foreign_holder_pid_detects_live_other(lock_path, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid

    lock_path.write_text("4242\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(os, "getpid", lambda: 1000)

    assert foreign_holder_pid(lock_path) == 4242


def test_foreign_holder_pid_ignores_stale(lock_path, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid

    lock_path.write_text("4242\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)

    assert foreign_holder_pid(lock_path) is None


def test_clear_if_stale_skips_live_foreign(lock_path, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale

    lock_path.write_text("4242\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(os, "getpid", lambda: 1000)

    assert clear_if_stale(lock_path) is False
    assert lock_path.is_file()


def test_clear_if_stale_removes_stale_lock(lock_path, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale

    lock_path.write_text("4242\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)

    assert clear_if_stale(lock_path) is True
    assert not lock_path.is_file()


def test_manual_act_blocked_when_foreign_lock(lock_path, monkeypatch):
    from plugins.sts2 import driver_lock

    lock_path.write_text("4242\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(os, "getpid", lambda: 1000)

    blocked = driver_lock.manual_act_blocked()
    assert blocked is not None
    assert "4242" in blocked


def test_release_all_driver_locks_preserves_foreign(lock_path, monkeypatch):
    from plugins.sts2.manual_mode import release_all_driver_locks

    lock_path.write_text("4242\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(os, "getpid", lambda: 1000)

    release_all_driver_locks()
    assert lock_path.is_file()
