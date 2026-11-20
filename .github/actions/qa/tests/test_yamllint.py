"""Verify YAML style checks reject long lines and accept GitHub's on key."""

import subprocess
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[4] / ".yamllint.yml"


def test_yamllint_accepts_github_on_key():
    result = subprocess.run(
        ["yamllint", "-c", str(CONFIG), "-"],
        input="on:\n  push:\n\npermissions: {}\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


def test_yamllint_rejects_long_values():
    result = subprocess.run(
        ["yamllint", "-c", str(CONFIG), "-"],
        input="value: " + "x" * 111 + "\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "line too long" in result.stdout
