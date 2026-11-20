"""Verify retry behavior through the composite action's entry point."""

import os
import subprocess
from pathlib import Path

import pytest

ENTRY_POINT = Path(__file__).resolve().parents[1] / "retry.sh"


@pytest.mark.parametrize(
    ("max_attempts", "success_at", "expected_status", "attempts"),
    [(3, 2, 0, 2), (3, 4, 1, 3), (1, 1, 0, 1), (1, 2, 1, 1)],
)
def test_retry_command(tmp_path, max_attempts, success_at, expected_status, attempts):
    counter = tmp_path / "counter"
    command = (
        'n=0; [ ! -f "$COUNTER" ] || read -r n < "$COUNTER"; '
        'n=$((n + 1)); printf "%s\\n" "$n" > "$COUNTER"; '
        f'[ "$n" -ge {success_at} ]'
    )
    env = os.environ | {
        "COMMAND": command,
        "COUNTER": str(counter),
        "MAX_ATTEMPTS": str(max_attempts),
        "DELAY_SECONDS": "0",
    }
    result = subprocess.run(
        ["bash", str(ENTRY_POINT)], env=env, capture_output=True, text=True
    )
    assert result.returncode == expected_status
    assert int(counter.read_text()) == attempts
    assert f"Attempt {attempts} of {max_attempts}" in result.stdout


def test_retry_does_not_mask_a_failure_in_a_pipeline():
    env = os.environ | {
        "COMMAND": "false | true",
        "MAX_ATTEMPTS": "2",
        "DELAY_SECONDS": "0",
    }
    result = subprocess.run(
        ["bash", str(ENTRY_POINT)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "Command failed after 2 attempts." in result.stdout
