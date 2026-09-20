"""Cross-process driver lock safety (no live game)."""

from __future__ import annotations

import json
import os

import pytest


@pytest.fixture
def sts2_env(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text(
        "sts2:\n  base_url: http://127.0.0.1:19999\n",
        encoding="utf-8",
    )
    return home


def test_foreign_holder_pid_detects_live_process(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid, try_acquire
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    assert try_acquire(lock, label="test")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == os.getpid(),
    )
    assert foreign_holder_pid(lock) is None

    lock.write_text(f"{os.getpid() + 99999}\nother\n", encoding="utf-8")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == os.getpid() + 99999,
    )
    assert foreign_holder_pid(lock) == os.getpid() + 99999


def test_clear_if_stale_skips_live_foreign_holder(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{os.getpid() + 12345}\nother\n", encoding="utf-8")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == os.getpid() + 12345,
    )
    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_clear_if_stale_removes_dead_holder(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999\nstale\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)
    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_manual_act_blocked_when_foreign_lock(sts2_env, monkeypatch):
    from plugins.sts2 import driver_lock
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    foreign_pid = os.getpid() + 777
    lock.write_text(f"{foreign_pid}\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == foreign_pid,
    )
    msg = driver_lock.manual_act_blocked()
    assert msg is not None
    assert str(foreign_pid) in msg
    assert lock.is_file()


def test_release_all_driver_locks_does_not_steal_foreign_lock(sts2_env, monkeypatch):
    from plugins.sts2.manual_mode import release_all_driver_locks
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    foreign_pid = os.getpid() + 888
    lock.write_text(f"{foreign_pid}\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == foreign_pid,
    )
    release_all_driver_locks()
    assert lock.is_file()
    assert lock.read_text(encoding="utf-8").startswith(f"{foreign_pid}\n")


def test_act_reports_api_error_as_failure(sts2_env, monkeypatch):
    from plugins.sts2.tools import handle_sts2_act

    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda body: (200, {"status": "error", "message": "Unknown action"}),
    )
    raw = handle_sts2_act({"action": "bad_action"})
    data = json.loads(raw)
    assert data["success"] is False
    assert data["status"] == "error"
