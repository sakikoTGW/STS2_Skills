"""plugins.sts2.process_lock — stale lock cleanup must not steal live locks."""

from __future__ import annotations

import os

from plugins.sts2.process_lock import clear_if_stale, lock_held_by_live_process


def test_clear_if_stale_removes_dead_pid(tmp_path, monkeypatch):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("999999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: False)

    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_clear_if_stale_preserves_live_pid(tmp_path, monkeypatch):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text(f"{os.getpid()}\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: True)

    assert lock_held_by_live_process(lock) is True
    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_clear_if_stale_removes_corrupt_lock(tmp_path, monkeypatch):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("not-a-pid\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: False)

    assert clear_if_stale(lock) is True
    assert not lock.is_file()
