"""Cross-process lock safety (no stealing live holder's lock file)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_clear_if_stale_removes_dead_holder(sts2_env, tmp_path: Path):
    from plugins.sts2.process_lock import clear_if_stale, holder_pid

    lock = tmp_path / ".autoplay.lock"
    lock.write_text("999999999\nstale\n", encoding="utf-8")
    assert holder_pid(lock) == 999999999
    assert clear_if_stale(lock) is True
    assert not lock.is_file()


def test_clear_if_stale_keeps_live_holder(sts2_env, tmp_path: Path):
    from plugins.sts2.process_lock import clear_if_stale, foreign_holder_pid

    lock = tmp_path / ".autoplay.lock"
    lock.write_text(f"{os.getpid()}\nautoplay\n", encoding="utf-8")
    assert clear_if_stale(lock) is False
    assert lock.is_file()
    assert foreign_holder_pid(lock) is None


def test_foreign_holder_pid_detects_other_process(sts2_env, tmp_path: Path):
    from plugins.sts2.process_lock import foreign_holder_pid

    lock = tmp_path / ".autoplay.lock"
    lock.write_text(f"{os.getpid()}\nautoplay\n", encoding="utf-8")
    assert foreign_holder_pid(lock) is None

    script = """
import os, sys, time
from pathlib import Path
from plugins.sts2.process_lock import try_acquire
lock = Path(sys.argv[1])
assert try_acquire(lock, label="child")
time.sleep(2)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", script, str(lock)],
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    try:
        for _ in range(50):
            pid = foreign_holder_pid(lock)
            if pid is not None and pid != os.getpid():
                break
            import time

            time.sleep(0.05)
        else:
            pytest.skip("child lock holder did not start in time")

        from plugins.sts2.process_lock import clear_if_stale

        assert clear_if_stale(lock) is False
        assert lock.is_file()
        assert foreign_holder_pid(lock) == proc.pid

        from plugins.sts2.driver_lock import manual_act_blocked

        blocked = manual_act_blocked()
        assert blocked is not None
        assert str(proc.pid) in blocked
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_sts2_act_blocked_when_foreign_lock(sts2_env, tmp_path: Path, monkeypatch):
    from plugins.sts2.driver_lock import manual_act_blocked
    from plugins.sts2.storage import sts2_home
    from plugins.sts2.tools import handle_sts2_act

    lock = sts2_home() / ".autoplay.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("424242\nautoplay\n", encoding="utf-8")

    monkeypatch.setattr(
        "plugins.sts2.process_lock._pid_alive",
        lambda pid: pid == 424242,
    )
    assert manual_act_blocked() is not None
    raw = handle_sts2_act({"action": "end_turn"})
    data = json.loads(raw)
    assert data.get("success") is False
    assert "424242" in str(data.get("error", ""))
