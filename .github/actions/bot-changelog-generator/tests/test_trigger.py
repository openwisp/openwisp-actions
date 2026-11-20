"""Exercise noteworthy pull request title detection through the entry point."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ENTRY_POINT = Path(__file__).resolve().parents[1] / "scripts/__main__.sh"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("[feature] Added feature", True),
        ("[FIX] Fixed issue", True),
        ("[change!] Removed compatibility", True),
        ("[docs] Updated documentation", False),
        ("prefix [fix] Corrected issue", False),
    ],
)
def test_noteworthy_title(tmp_path, title, expected):
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", str(ENTRY_POINT), "check-title"],
        env=os.environ | {"PR_TITLE": title, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    if expected:
        assert output.read_text() == "has_noteworthy=true\n"
    else:
        assert not output.exists()


def test_trigger_checks_out_trusted_default_branch():
    workflow = ENTRY_POINT.parents[3] / "workflows/bot-changelog-trigger.yml"
    data = yaml.safe_load(workflow.read_text())
    checkout = data["jobs"]["check"]["steps"][0]
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert checkout["with"]["persist-credentials"] is False
