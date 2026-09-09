"""Cross-process lock and sts2_act safety tests."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

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


def test_act_reports_api_error_as_failure(sts2_env, monkeypatch):
    from plugins.sts2.tools import handle_sts2_act

    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        lambda body: (200, {"status": "error", "message": "invalid card index"}),
    )
    raw = handle_sts2_act({"action": "play_card", "card_index": 99})
    data = json.loads(raw)
    assert data["success"] is False
    assert "invalid card index" in data.get("error", "")


def test_foreign_holder_pid_detects_other_process(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 424242)
    assert foreign_holder_pid(lock) == 424242


def test_foreign_holder_pid_ignores_self(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{os.getpid()}\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: True)
    assert foreign_holder_pid(lock) is None


def test_clear_if_stale_removes_dead_holder(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("99999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: False)
    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_clear_if_stale_keeps_live_foreign_holder(sts2_env, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 424242)
    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_manual_act_blocked_by_foreign_lock(sts2_env, monkeypatch):
    from plugins.sts2 import driver_lock
    from plugins.sts2.storage import sts2_home
    from plugins.sts2.tools import handle_sts2_act

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 424242)
    monkeypatch.setattr(
        "plugins.sts2.client.post_singleplayer_action",
        MagicMock(return_value=(200, {"status": "ok"})),
    )
    raw = handle_sts2_act({"action": "end_turn"})
    data = json.loads(raw)
    assert data.get("success") is False or "error" in data
    assert "blocked" in str(data.get("error", raw)).lower()
    assert driver_lock.active_mode() is None


def test_release_all_driver_locks_does_not_steal_foreign_lock(sts2_env, monkeypatch):
    from plugins.sts2.manual_mode import release_all_driver_locks
    from plugins.sts2.storage import sts2_home

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 424242)
    release_all_driver_locks()
    assert lock.is_file()
    assert lock.read_text(encoding="utf-8").startswith("424242")
