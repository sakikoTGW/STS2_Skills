"""plugins.sts2.process_lock — cross-process lock safety."""

from __future__ import annotations

import os
from pathlib import Path

from plugins.sts2 import process_lock


def test_clear_if_stale_keeps_live_foreign_lock(tmp_path, monkeypatch):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("99999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(process_lock, "_pid_alive", lambda pid: pid == 99999)
    assert process_lock.foreign_holder_pid(lock) == 99999
    assert process_lock.clear_if_stale(lock) is False
    assert lock.is_file()


def test_clear_if_stale_removes_dead_holder(tmp_path, monkeypatch):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("99999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(process_lock, "_pid_alive", lambda _pid: False)
    assert process_lock.foreign_holder_pid(lock) is None
    assert process_lock.clear_if_stale(lock) is True
    assert not lock.is_file()


def test_clear_if_stale_removes_corrupt_lock(tmp_path):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("not-a-pid\n", encoding="utf-8")
    assert process_lock.clear_if_stale(lock) is True
    assert not lock.is_file()


def test_foreign_holder_ignores_own_pid(tmp_path):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text(f"{os.getpid()}\nautoplay\n", encoding="utf-8")
    assert process_lock.foreign_holder_pid(lock) is None
