"""Cross-process lock helpers (no live game)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.fixture
def lock_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def test_foreign_holder_pid_detects_live_other(lock_home):
    from plugins.sts2.process_lock import foreign_holder_pid, try_acquire
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")

    with patch("plugins.sts2.process_lock._pid_alive", return_value=True):
        assert foreign_holder_pid(lock) == 424242


def test_foreign_holder_pid_ignores_self(lock_home):
    from plugins.sts2.process_lock import foreign_holder_pid, try_acquire
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    assert try_acquire(lock, label="test")
    assert foreign_holder_pid(lock) is None


def test_clear_if_stale_removes_dead_holder(lock_home):
    from plugins.sts2.process_lock import clear_if_stale
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("99999\nautoplay\n", encoding="utf-8")

    with patch("plugins.sts2.process_lock._pid_alive", return_value=False):
        assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_clear_if_stale_keeps_live_foreign(lock_home):
    from plugins.sts2.process_lock import clear_if_stale
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")

    with patch("plugins.sts2.process_lock._pid_alive", return_value=True):
        assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_manual_act_blocked_by_foreign_lock(lock_home):
    from plugins.sts2.driver_lock import manual_act_blocked
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")

    with patch("plugins.sts2.process_lock._pid_alive", return_value=True):
        blocked = manual_act_blocked()
    assert blocked is not None
    assert "424242" in blocked


def test_release_all_driver_locks_does_not_steal_foreign(lock_home):
    from plugins.sts2.manual_mode import release_all_driver_locks
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")

    with patch("plugins.sts2.process_lock._pid_alive", return_value=True):
        release_all_driver_locks()
    assert lock.is_file()


def test_release_all_driver_locks_clears_stale(lock_home):
    from plugins.sts2.manual_mode import release_all_driver_locks
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("99999\nautoplay\n", encoding="utf-8")

    with patch("plugins.sts2.process_lock._pid_alive", return_value=False):
        release_all_driver_locks()
    assert not lock.is_file()
