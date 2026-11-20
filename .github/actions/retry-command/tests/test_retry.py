"""Verify retry behavior through the composite action's entry point."""

import os
import subprocess
from pathlib import Path

import pytest

ENTRY_POINT = Path(__file__).resolve().parents[1] / "scripts/__main__.sh"


@pytest.mark.parametrize(
    ("success_at", "expected_status", "attempts"), [(2, 0, 2), (4, 1, 3)]
)
def test_retry_command(tmp_path, success_at, expected_status, attempts):
    counter = tmp_path / "counter"
    command = (
        'n=0; [ ! -f "$COUNTER" ] || read -r n < "$COUNTER"; '
        'n=$((n + 1)); printf "%s\\n" "$n" > "$COUNTER"; '
        f'[ "$n" -ge {success_at} ]'
    )
    env = os.environ | {
        "COMMAND": command,
        "COUNTER": str(counter),
        "MAX_ATTEMPTS": "3",
        "DELAY_SECONDS": "0",
    }
    result = subprocess.run(
        ["bash", str(ENTRY_POINT)], env=env, capture_output=True, text=True
    )
    assert result.returncode == expected_status
    assert int(counter.read_text()) == attempts
    assert f"Attempt {attempts} of 3" in result.stdout
