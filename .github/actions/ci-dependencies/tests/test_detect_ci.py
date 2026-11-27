"""Check that repositories opt into the shared CI convention."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "reusable" / "detect_ci.sh"


@pytest.mark.parametrize(
    ("workflow", "expected"),
    [
        (None, "false"),
        ("jobs:\n  build:\n    steps: []\n", "false"),
        ("jobs:\n  test:\n    steps:\n      - run: ./install-ci-deps.sh\n", "false"),
        (
            "jobs:\n  test:\n    steps:\n      - id: deps\n        run: ./install-ci-deps.sh\n",
            "true",
        ),
    ],
)
def test_detects_only_standard_ci(tmp_path, workflow, expected):
    ci = tmp_path / ".github" / "workflows" / "ci.yml"
    if workflow is not None:
        ci.parent.mkdir(parents=True)
        ci.write_text(workflow)
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "CI_ROOT": str(tmp_path), "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text().strip() == f"enabled={expected}"


def test_openwisp_actions_ci_opts_into_dependency_reuse(tmp_path):
    root = SCRIPT.parents[4]
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "CI_ROOT": str(root), "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text().strip() == "enabled=true"
    assert os.access(root / "install-ci-deps.sh", os.X_OK)
