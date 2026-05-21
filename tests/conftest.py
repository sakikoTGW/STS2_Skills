"""Shared pytest fixtures for sts2-skills standalone tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_sts2_home(tmp_path, monkeypatch):
    home = tmp_path / "sts2home"
    home.mkdir()
    monkeypatch.setenv("STS2_HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


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
