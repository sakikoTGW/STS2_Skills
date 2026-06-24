"""Cross-process lock safety for autoplay driver."""

from __future__ import annotations

import json
import os

from plugins.sts2.process_lock import clear_if_stale, foreign_holder_pid, try_acquire


def test_clear_if_stale_removes_dead_holder(tmp_path):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("999999999\nautoplay\n")
    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_clear_if_stale_keeps_live_foreign(monkeypatch, tmp_path):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("12345\nautoplay\n")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive", lambda pid: pid == 12345
    )
    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_foreign_holder_pid_detects_other_process(monkeypatch, tmp_path):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("12345\nautoplay\n")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive", lambda pid: pid == 12345
    )
    assert foreign_holder_pid(lock) == 12345


def test_foreign_holder_pid_ignores_self(tmp_path):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text(f"{os.getpid()}\nautoplay\n")
    assert foreign_holder_pid(lock) is None


def test_manual_act_blocked_by_foreign_lock(monkeypatch, sts2_env):
    from plugins.sts2.storage import sts2_home
    from plugins.sts2.tools import handle_sts2_act

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("42424\nautoplay\n")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive", lambda pid: pid == 42424
    )

    raw = handle_sts2_act({"action": "end_turn"})
    data = json.loads(raw)
    assert data.get("success") is False
    assert "42424" in str(data.get("error", ""))


def test_try_acquire_respects_live_foreign(monkeypatch, tmp_path):
    lock = tmp_path / ".autoplay.lock"
    lock.write_text("77777\nautoplay\n")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive", lambda pid: pid == 77777
    )
    assert try_acquire(lock, label="autoplay") is False
