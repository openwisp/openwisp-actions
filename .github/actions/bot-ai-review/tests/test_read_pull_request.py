"""Test the pull request references passed to the review gate."""

import json
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "reusable/read_pull_request.sh"


def test_records_base_branch_with_commit_references(tmp_path):
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$PR_JSON"\n')
    gh.chmod(0o755)
    output = tmp_path / "output"
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "REPOSITORY": "o/r",
        "PR_NUMBER": "1",
        "GITHUB_OUTPUT": str(output),
        "PR_JSON": json.dumps(
            {"head": {"sha": "a" * 40}, "base": {"sha": "b" * 40, "ref": "release"}}
        ),
    }
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "base_ref=release\n" in output.read_text()


def test_rejects_base_branch_that_could_inject_workflow_outputs(tmp_path):
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$PR_JSON"\n')
    gh.chmod(0o755)
    output = tmp_path / "output"
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "REPOSITORY": "o/r",
        "PR_NUMBER": "1",
        "GITHUB_OUTPUT": str(output),
        "PR_JSON": json.dumps(
            {
                "head": {"sha": "a" * 40},
                "base": {"sha": "b" * 40, "ref": "main\nstage=review"},
            }
        ),
    }
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True)
    assert result.returncode != 0
    assert not output.exists()
