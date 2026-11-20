"""Verify the assignment bot entry point rejects unknown commands."""

import os
import subprocess
import sys
from pathlib import Path

ENTRY_POINT = Path(__file__).resolve().parents[1] / "scripts/__main__.py"


def test_unknown_bot_command_fails():
    result = subprocess.run(
        [sys.executable, str(ENTRY_POINT), "unknown"], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "Unknown bot type: unknown" in result.stdout


def test_rejects_empty_validation_repository_list():
    result = subprocess.run(
        [sys.executable, str(ENTRY_POINT), "validate-repositories"],
        env=os.environ | {"PUBLIC_VALIDATION_REPOSITORIES": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "prevent minting a token with org-wide access" in result.stdout


def test_accepts_nonempty_validation_repository_list():
    result = subprocess.run(
        [sys.executable, str(ENTRY_POINT), "validate-repositories"],
        env=os.environ | {"PUBLIC_VALIDATION_REPOSITORIES": "openwisp/example"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
