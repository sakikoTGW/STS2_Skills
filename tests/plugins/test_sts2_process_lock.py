"""plugins.sts2.process_lock — stale lock cleanup must not steal live locks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_clear_if_stale_removes_dead_pid_lock(tmp_path, monkeypatch):
    from plugins.sts2 import process_lock

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("999999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(process_lock, "_pid_alive", lambda pid: False)

    assert process_lock.clear_if_stale(lock) is True
    assert not lock.is_file()


def test_clear_if_stale_keeps_live_pid_lock(tmp_path, monkeypatch):
    from plugins.sts2 import process_lock

    lock = tmp_path / ".autoplay.lock"
    lock.write_text(f"{os.getpid()}\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(process_lock, "_pid_alive", lambda pid: pid == os.getpid())

    assert process_lock.clear_if_stale(lock) is False
    assert lock.is_file()


def test_clear_if_stale_removes_unparseable_lock(tmp_path):
    from plugins.sts2 import process_lock

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("not-a-pid\n", encoding="utf-8")

    assert process_lock.clear_if_stale(lock) is True
    assert not lock.is_file()
