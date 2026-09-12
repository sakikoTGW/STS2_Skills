"""Cross-process driver lock safety."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def test_foreign_holder_pid_detects_live_other(tmp_path, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid, try_acquire

    lock = tmp_path / ".autoplay.lock"
    monkeypatch.setattr("plugins.sts2.storage.sts2_home", lambda: tmp_path)

    assert foreign_holder_pid(lock) is None

    other_pid = os.getpid() + 99999
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{other_pid}\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == other_pid,
    )
    assert foreign_holder_pid(lock) == other_pid


def test_foreign_holder_pid_ignores_dead_holder(tmp_path, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale, foreign_holder_pid

    lock = tmp_path / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("99999\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)
    assert foreign_holder_pid(lock) is None
    assert clear_if_stale(lock) is True
    assert not lock.exists()


def test_clear_if_stale_keeps_live_foreign_lock(tmp_path, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale

    lock = tmp_path / ".autoplay.lock"
    other_pid = 424242
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{other_pid}\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == other_pid,
    )
    assert clear_if_stale(lock) is False
    assert lock.exists()


def test_manual_act_blocked_by_foreign_lock(tmp_path, monkeypatch):
    from plugins.sts2 import driver_lock

    monkeypatch.setattr("plugins.sts2.storage.sts2_home", lambda: tmp_path)
    lock = tmp_path / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("55555\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 55555)

    blocked = driver_lock.manual_act_blocked()
    assert blocked is not None
    assert "55555" in blocked


def test_release_all_driver_locks_does_not_steal_foreign(tmp_path, monkeypatch):
    from plugins.sts2.manual_mode import release_all_driver_locks

    monkeypatch.setattr("plugins.sts2.storage.sts2_home", lambda: tmp_path)
    lock = tmp_path / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("66666\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 66666)

    release_all_driver_locks()
    assert lock.exists()
    assert lock.read_text(encoding="utf-8").startswith("66666")


def test_act_reports_api_error_as_failure(sts2_env, monkeypatch):
    from plugins.sts2.tools import handle_sts2_act

    def fake_post(body):
        return 200, {"status": "error", "message": "illegal action"}

    monkeypatch.setattr("plugins.sts2.client.post_singleplayer_action", fake_post)
    monkeypatch.setattr(
        "plugins.sts2.client.get_singleplayer_state",
        lambda **kw: (200, {"state_type": "map"}),
    )
    monkeypatch.setattr(
        "plugins.sts2.action_validate.validate_action",
        lambda state, body: body,
    )

    raw = handle_sts2_act({"action": "end_turn"})
    data = json.loads(raw)
    assert data.get("success") is False
    assert "illegal action" in str(data.get("error", ""))
