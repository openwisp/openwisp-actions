"""Check line length enforcement for maintained shell scripts."""

import subprocess
import sys
from pathlib import Path

ENTRY_POINT = Path(__file__).resolve().parents[1] / "scripts/__main__.py"


def test_line_length_detects_nested_and_extensionless_scripts(tmp_path):
    nested = tmp_path / ".github/actions/example/scripts"
    nested.mkdir(parents=True)
    (nested / "helper.sh").write_text("#!/bin/sh\n# " + "x" * 109 + "\n")
    (nested / "helper.bash").write_text("#!/bin/bash\n# " + "x" * 109 + "\n")
    (tmp_path / "runtests").write_text("#!/usr/bin/env bash\n# " + "x" * 109 + "\n")
    ignored = tmp_path / ".venv"
    ignored.mkdir()
    (ignored / "activate.sh").write_text("# " + "x" * 200 + "\n")
    result = subprocess.run(
        [sys.executable, str(ENTRY_POINT), "line-length", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "helper.sh:2" in result.stdout
    assert "helper.bash:2" in result.stdout
    assert "runtests:2" in result.stdout
    assert ".venv" not in result.stdout


def test_line_length_accepts_boundary(tmp_path):
    (tmp_path / "script.sh").write_text("# " + "x" * 108 + "\n")
    result = subprocess.run(
        [sys.executable, str(ENTRY_POINT), "line-length", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
