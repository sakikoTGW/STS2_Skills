"""Cross-process autoplay lock safety."""

from __future__ import annotations

import os
from pathlib import Path


def test_clear_stale_lock_skips_live_foreign_holder(monkeypatch, tmp_path):
    from plugins.sts2 import process_lock

    lock = tmp_path / ".autoplay.lock"
    foreign = os.getpid() + 999_999
    lock.write_text(f"{foreign}\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(process_lock, "_pid_alive", lambda pid: pid == foreign)

    assert process_lock.foreign_lock_held(lock) is True
    assert process_lock.clear_stale_lock(lock) is False
    assert lock.is_file()


def test_clear_stale_lock_removes_dead_holder(monkeypatch, tmp_path):
    from plugins.sts2 import process_lock

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("999999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(process_lock, "_pid_alive", lambda _pid: False)

    assert process_lock.lock_holder_stale(lock) is True
    assert process_lock.clear_stale_lock(lock) is True
    assert not lock.exists()


def test_manual_act_blocked_when_foreign_lock(monkeypatch, tmp_path):
    from plugins.sts2 import driver_lock, process_lock
    from plugins.sts2.storage import sts2_home
    from plugins.sts2.tools import handle_sts2_act

    lock = sts2_home() / ".autoplay.lock"
    foreign = os.getpid() + 888_888
    lock.write_text(f"{foreign}\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(process_lock, "_pid_alive", lambda pid: pid == foreign)

    raw = handle_sts2_act({"action": "end_turn"})
    assert "another process" in raw.lower()
    driver_lock.release("autoplay")
