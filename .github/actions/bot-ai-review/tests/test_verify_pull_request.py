"""Test that a review does not start after the pull request changes."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "reusable/verify_pull_request.sh"


def test_only_open_requested_revision_can_start(tmp_path):
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$PR_STATE" "$PR_HEAD" "$PR_BASE"\n')
    gh.chmod(0o755)
    for state, head, base, expected in (
        ("open", "abc", "master", 0),
        ("closed", "abc", "master", 1),
        ("open", "def", "master", 1),
        ("open", "abc", "release", 1),
    ):
        env = {
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "REPOSITORY": "o/r",
            "PR_NUMBER": "1",
            "HEAD_SHA": "abc",
            "BASE_REF": "master",
            "PR_STATE": state,
            "PR_HEAD": head,
            "PR_BASE": base,
        }
        result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True)
        assert (result.returncode == 0) == (expected == 0)
