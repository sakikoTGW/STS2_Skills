"""scripts/detect_install_paths.py"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_detect_install_paths_json():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "detect_install_paths.py"), "--host", "standalone", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["host"] == "standalone"
    assert "host_path" in data
    assert "skills_dir" in data
    assert "python" in data
