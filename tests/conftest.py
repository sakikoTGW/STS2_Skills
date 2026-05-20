"""Minimal pytest fixtures for hermes-sts2 standalone tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_sts2_home(tmp_path, monkeypatch):
    home = tmp_path / "sts2home"
    home.mkdir()
    monkeypatch.setenv("STS2_HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
