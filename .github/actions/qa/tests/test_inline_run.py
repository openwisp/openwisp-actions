"""Verify YAML-aware limits on workflow and composite action run blocks."""

import subprocess
import sys
from pathlib import Path

ENTRY_POINT = Path(__file__).resolve().parents[1] / "scripts/__main__.py"


def run_check(root):
    return subprocess.run(
        [sys.executable, str(ENTRY_POINT), "inline-run", str(root)],
        capture_output=True,
        text=True,
    )


def test_rejects_long_block_and_ignores_multiline_env(tmp_path):
    workflow = tmp_path / ".github/workflows"
    workflow.mkdir(parents=True)
    (workflow / "test.yml").write_text(
        "jobs:\n  test:\n    steps:\n      - env:\n          TEXT: |\n"
        + "            text\n" * 8
        + "        run: |\n"
        + "          command\n" * 6
    )
    result = run_check(tmp_path)
    assert result.returncode != 0
    assert "test.yml" in result.stdout
    assert "6 lines" in result.stdout


def test_accepts_five_line_composite_action(tmp_path):
    action = tmp_path / ".github/actions/example"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(
        "runs:\n  steps:\n    - run: |\n" + "        command\n" * 5
    )
    result = run_check(tmp_path)
    assert result.returncode == 0, result.stdout


def test_ignores_env_variable_named_run(tmp_path):
    workflow = tmp_path / ".github/workflows"
    workflow.mkdir(parents=True)
    (workflow / "test.yml").write_text(
        "jobs:\n  test:\n    steps:\n      - env:\n          run: |\n"
        + "            text\n" * 8
        + "        run: echo ok\n"
    )
    result = run_check(tmp_path)
    assert result.returncode == 0, result.stdout
