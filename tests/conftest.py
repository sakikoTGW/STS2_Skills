"""Shared pytest fixtures for sts2-skills standalone tests."""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest


def _ensure_agent_stub() -> None:
    """Hermes ``agent.auxiliary_client`` is optional; tests monkeypatch call_llm."""
    if "agent.auxiliary_client" in sys.modules:
        return
    agent_mod = sys.modules.get("agent")
    if agent_mod is None:
        agent_mod = ModuleType("agent")
        sys.modules["agent"] = agent_mod
    aux = ModuleType("agent.auxiliary_client")

    def _default_call_llm(*args, **kwargs) -> str:
        return '{"commentary":"","action":"end_turn"}'

    aux.call_llm = _default_call_llm  # type: ignore[attr-defined]
    agent_mod.auxiliary_client = aux  # type: ignore[attr-defined]
    sys.modules["agent.auxiliary_client"] = aux


_ensure_agent_stub()


@pytest.fixture(autouse=True)
def _isolate_sts2_home(tmp_path, monkeypatch):
    home = tmp_path / "sts2home"
    home.mkdir()
    monkeypatch.setenv("STS2_HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


@pytest.fixture(autouse=True)
def _reset_sts2_driver_lock():
    """Avoid cross-test driver lock pollution."""
    from plugins.sts2 import driver_lock

    for mode in ("autoplay", "manual", "watch", "learn"):
        driver_lock.release(mode)
    yield
    for mode in ("autoplay", "manual", "watch", "learn"):
        driver_lock.release(mode)


@pytest.fixture
def sts2_env(monkeypatch, tmp_path):
    """Hermes-style config dir for tests that call load_sts2_config / tools."""
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text(
        "sts2:\n  base_url: http://127.0.0.1:19999\n",
        encoding="utf-8",
    )
    return home
