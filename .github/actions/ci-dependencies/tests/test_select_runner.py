"""Check that reviews use the runner image of the trusted CI test job."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parent.parent / "reusable" / "select_runner.sh"
WORKFLOW = (
    Path(__file__).resolve().parents[3] / "workflows" / "reusable-bot-ai-review.yml"
)


def select(tmp_path, workflow=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    if workflow is None:
        gh.write_text("#!/bin/sh\nexit 1\n")
    else:
        (tmp_path / "ci.yml").write_text(workflow)
        gh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >"$ARGS"\ncat "$CI_WORKFLOW"\n')
    gh.chmod(0o755)
    output = tmp_path / "output"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ARGS": str(tmp_path / "args"),
        "CI_WORKFLOW": str(tmp_path / "ci.yml"),
        "GITHUB_OUTPUT": str(output),
        "REPOSITORY": "openwisp/repo",
        "BASE_SHA": "base",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return output.read_text(), result.stdout


@pytest.mark.parametrize("runner", ["ubuntu-22.04", "ubuntu-24.04", "ubuntu-latest"])
def test_uses_hosted_ubuntu_runner_of_ci(tmp_path, runner):
    output, stdout = select(tmp_path, f"jobs:\n  test:\n    runs-on: {runner}\n")
    assert output == f"runner={runner}\n"
    assert stdout == ""
    assert (
        "repos/openwisp/repo/contents/.github/workflows/ci.yml?ref=base"
        in (tmp_path / "args").read_text().splitlines()
    )


@pytest.mark.parametrize(
    "runner",
    ["self-hosted", "macos-15", "[self-hosted, linux]", "${{ matrix.os }}"],
)
def test_other_runners_fall_back_with_a_warning(tmp_path, runner):
    output, stdout = select(tmp_path, f"jobs:\n  test:\n    runs-on: {runner}\n")
    assert output == "runner=ubuntu-latest\n"
    assert "Unsupported CI runner" in stdout


@pytest.mark.parametrize("workflow", [None, "jobs:\n  lint: {}\n"])
def test_missing_ci_test_job_uses_default_runner(tmp_path, workflow):
    output, stdout = select(tmp_path, workflow)
    assert output == "runner=ubuntu-latest\n"
    assert stdout == ""


def test_review_job_runs_on_selected_runner():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    step = next(item for item in jobs["gate"]["steps"] if item.get("id") == "runner")
    assert step["env"]["BASE_SHA"] == "${{ steps.coordinate.outputs.base_sha }}"
    assert jobs["gate"]["outputs"]["runner"] == "${{ steps.runner.outputs.runner }}"
    assert jobs["review"]["runs-on"] == (
        "${{ needs.gate.outputs.runner || 'ubuntu-latest' }}"
    )
