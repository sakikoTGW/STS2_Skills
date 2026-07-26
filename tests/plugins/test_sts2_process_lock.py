"""Cross-process lock helpers (no live game)."""

from __future__ import annotations

import json
import os

import pytest


def test_foreign_holder_pid_detects_other_live_process(sts2_env, tmp_path, monkeypatch):
    from plugins.sts2.process_lock import foreign_holder_pid

    lock = tmp_path / ".autoplay.lock"
    lock.write_text(f"{os.getpid()}\nautoplay\n", encoding="utf-8")
    assert foreign_holder_pid(lock) is None

    lock.write_text("999999\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 999999)
    assert foreign_holder_pid(lock) == 999999


def test_clear_if_stale_skips_foreign_holder(sts2_env, tmp_path, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 424242)

    assert clear_if_stale(lock) is False
    assert lock.is_file()


def test_clear_if_stale_removes_dead_holder(sts2_env, tmp_path, monkeypatch):
    from plugins.sts2.process_lock import clear_if_stale

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("424242\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda _pid: False)

    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_foreign_autoplay_lock_blocks_manual_act(sts2_env, tmp_path, monkeypatch):
    from plugins.sts2.storage import sts2_home
    from plugins.sts2.tools import handle_sts2_act

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("777777\nautoplay\n", encoding="utf-8")
    monkeypatch.setattr("plugins.sts2.process_lock._pid_alive", lambda pid: pid == 777777)
    monkeypatch.setattr(
        "plugins.sts2.config.enforce_single_driver_enabled",
        lambda: True,
    )

    raw = handle_sts2_act({"action": "end_turn"})
    data = json.loads(raw)
    assert data.get("success") is False
    assert "777777" in str(data.get("error", ""))
