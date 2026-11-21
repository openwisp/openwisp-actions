"""Verify the workflow inline-script limit without running workflow code."""

import subprocess
import sys
from pathlib import Path

import pytest

CHECK = Path(__file__).resolve().parent / "enforce_lean_yaml.py"


@pytest.mark.parametrize(
    ("style", "count", "valid"), [("|", 5, True), ("|", 6, False), (">", 6, False)]
)
def test_counts_run_block_source_lines(tmp_path, style, count, valid):
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        f"jobs:\n  test:\n    steps:\n      - run: {style}\n"
        + "          command\n" * count
    )
    result = subprocess.run(
        [sys.executable, str(CHECK), str(tmp_path)], capture_output=True, text=True
    )
    assert (result.returncode == 0) is valid
    if not valid:
        assert "6 lines" in result.stdout


def test_ignores_multiline_environment_variable_named_run(tmp_path):
    actions = tmp_path / ".github/actions/example"
    actions.mkdir(parents=True)
    (actions / "action.yml").write_text(
        "runs:\n  steps:\n    - env:\n        run: |\n"
        + "          data\n" * 6
        + "      run: echo ok\n"
    )
    result = subprocess.run(
        [sys.executable, str(CHECK), str(tmp_path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
