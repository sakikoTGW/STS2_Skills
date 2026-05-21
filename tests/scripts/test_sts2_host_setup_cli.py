"""CLI wrapper used by sts2skill.exe installer."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_host_setup_cli_json(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "sts2_host_setup_cli.py"
    game = tmp_path / "game"
    game.mkdir()
    (game / "SlayTheSpire2.exe").write_text("", encoding="utf-8")
    sts2_home = tmp_path / ".config" / "sts2"
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--host",
            "standalone",
            "--repo-root",
            str(repo),
            "--game-dir",
            str(game),
            "--sts2-home",
            str(sts2_home),
            "--character",
            "1",
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo),
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["host"] == "standalone"
    assert (sts2_home / "config.yaml").is_file()
