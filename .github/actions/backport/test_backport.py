"""Exercise the reusable backport workflow with local Git repositories."""

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[2] / "workflows/reusable-backport.yml"


@pytest.mark.parametrize(
    ("pr_data", "message", "expected_title", "expected_body"),
    [
        (
            "null",
            "[fix] Corrected checksum\n\nFirst paragraph.\n\n[backport 1.3]",
            "[backport] [fix] Corrected checksum (to 1.3)",
            "Backport of commit {sha} to `1.3`.\n\n"
            "First paragraph.\n\n[backport 1.3]",
        ),
        (
            "null",
            "[fix] Corrected checksum",
            "[backport] [fix] Corrected checksum (to 1.3)",
            "Backport of commit {sha} to `1.3`.",
        ),
        (
            '{"number": 42, "title": "Fixed checksum"}',
            "[fix] Corrected checksum\n\nCommit details",
            "[backport] #42: Fixed checksum (to 1.3)",
            "Backport of #42 to `1.3`.",
        ),
    ],
)
def test_backport_pr_metadata(
    tmp_path, pr_data, message, expected_title, expected_body
):
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-b", "master")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    (repo / "file").write_text("initial\n")
    git("add", "file")
    git("commit", "-m", "Initial")
    remote = tmp_path / "remote.git"
    git("init", "--bare", str(remote))
    git("remote", "add", "origin", str(remote))
    git("branch", "1.3")
    git("push", "origin", "1.3")
    (repo / "file").write_text("changed\n")
    git("commit", "-am", message)
    sha = git("rev-parse", "HEAD")

    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "if sys.argv[1] == 'api':\n"
        "    print(os.environ['PR_DATA'])\n"
        "elif sys.argv[1:3] == ['pr', 'create']:\n"
        "    with open(os.environ['PR_OUTPUT'], 'w') as output:\n"
        "        json.dump(sys.argv[3:], output)\n"
    )
    gh.chmod(0o755)
    output = tmp_path / "pr.json"
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "SHA": sha,
        "BRANCH": "1.3",
        "REPO": "example/repo",
        "PR_DATA": pr_data,
        "PR_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
    }
    script = WORKFLOW.read_text().split("      - name: Cherry-pick and create PR\n")[1]
    script = textwrap.dedent(script.split("        run: |\n", 1)[1])
    subprocess.run(["bash", "-e", "-c", script], cwd=repo, env=env, check=True)
    args = json.loads(output.read_text())
    assert args[args.index("--title") + 1] == expected_title
    assert args[args.index("--body") + 1] == expected_body.format(sha=sha)
