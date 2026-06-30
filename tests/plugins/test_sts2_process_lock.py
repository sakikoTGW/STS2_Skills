"""Cross-process lock helpers (no live game)."""

from __future__ import annotations

import os
from pathlib import Path

from plugins.sts2.process_lock import clear_if_stale, foreign_holder_pid


def test_foreign_holder_pid_detects_live_other(tmp_path, monkeypatch):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 424242)
    assert foreign_holder_pid(lock) == 424242


def test_foreign_holder_pid_ignores_self(tmp_path, monkeypatch):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text(f"{os.getpid()}\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: True)
    assert foreign_holder_pid(lock) is None


def test_clear_if_stale_removes_dead_holder(tmp_path, monkeypatch):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("99999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)
    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_clear_if_stale_keeps_live_foreign(tmp_path, monkeypatch):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 424242)
    assert clear_if_stale(lock) is False
    assert lock.is_file()
