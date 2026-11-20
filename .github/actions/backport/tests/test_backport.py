"""Exercise the reusable backport workflow with local Git repositories."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ENTRY_POINT = Path(__file__).resolve().parents[1] / "scripts/__main__.sh"


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
        "if sys.argv[1:3] == ['api', '--method']:\n"
        "    print('[[]]')\n"
        "elif sys.argv[1] == 'api':\n"
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
    subprocess.run(
        ["bash", str(ENTRY_POINT), "backport"],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    args = json.loads(output.read_text())
    assert args[args.index("--title") + 1] == expected_title
    assert args[args.index("--body") + 1] == expected_body.format(sha=sha)


@pytest.mark.parametrize(
    ("commit_sha", "response", "comment", "branches", "sha"),
    [
        ("abc123", "Fix\n\n[backport 1.2,1.3]", "", ["1.2", "1.3"], "abc123"),
        ("abc123", "Fix without backport", "", [], "abc123"),
        (
            "",
            '{"state":"MERGED","mergeCommit":{"oid":"def456"}}',
            "/backport 1.3",
            ["1.3"],
            "def456",
        ),
        ("", '{"state":"OPEN","mergeCommit":null}', "/backport 1.3", [], ""),
    ],
)
def test_parse_backport_request(tmp_path, commit_sha, response, comment, branches, sha):
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$GH_RESPONSE"\n')
    gh.chmod(0o755)
    output = tmp_path / "output"
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "COMMIT_SHA": commit_sha,
        "PR_NUMBER": "42",
        "COMMENT_BODY": comment,
        "REPO": "example/repo",
        "GH_RESPONSE": response,
        "GITHUB_OUTPUT": str(output),
    }
    subprocess.run(
        ["bash", str(ENTRY_POINT), "parse"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    result = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert json.loads(result["branches"]) == branches
    assert result["sha"] == sha


@pytest.mark.parametrize(
    "scenario",
    [
        "empty",
        "conflict",
        "create_failure",
        "push_failure",
        "invalid_branch",
        "missing_branch",
        "lookup_failure",
        "existing_pr",
        "merge_commit",
    ],
)
def test_backport_failure_paths(tmp_path, scenario):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

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
    (repo / "file").write_text("change\n")
    git("commit", "-am", "Source change")
    sha = git("rev-parse", "HEAD")
    if scenario == "empty":
        git("branch", "-f", "1.3", sha)
    elif scenario == "conflict":
        git("checkout", "1.3")
        (repo / "file").write_text("different change\n")
        git("commit", "-am", "Conflicting change")
        git("checkout", "master")
    elif scenario == "merge_commit":
        git("branch", "feature")
        git("reset", "--hard", "HEAD^")
        git("merge", "--no-ff", "feature", "-m", "Merge feature")
        sha = git("rev-parse", "HEAD")
    git("push", "origin", "1.3")
    if scenario == "push_failure":
        hook = remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)

    gh = tmp_path / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'if [ "$1 $2" = "api --method" ]; then\n'
        '  [ "$3 $4 $5" = "GET --paginate --slurp" ] || exit 3\n'
        '  [ "$6" = "repos/example/repo/pulls" ] || exit 3\n'
        '  [ "$7 $8 $9 ${10}" = "-f state=open -f base=1.3" ] || exit 3\n'
        '  [ "$FAIL_LOOKUP" != 1 ] || exit 1\n'
        '  printf "%s\\n" "$OPEN_PRS"\n'
        'elif [ "$1" = api ]; then\n'
        '  printf \'%s\\n\' \'{"number":42,"title":"Source"}\'\n'
        "elif [ \"$1 $2\" = 'pr create' ]; then\n"
        '  touch "$CREATE_ATTEMPT"\n'
        "  exit 1\n"
        "elif [ \"$1 $2\" = 'pr comment' ]; then\n"
        '  if [ "$4" = --body-file ]; then cp "$5" "$COMMENT_OUTPUT";\n'
        '  else printf "%s\\n" "$5" > "$COMMENT_OUTPUT"; fi\n'
        "fi\n"
    )
    gh.chmod(0o755)
    summary = tmp_path / "summary"
    comment = tmp_path / "comment"
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "SHA": sha,
        "BRANCH": {"invalid_branch": "invalid branch", "missing_branch": "1.4"}.get(
            scenario, "1.3"
        ),
        "REPO": "example/repo",
        "GITHUB_STEP_SUMMARY": str(summary),
        "COMMENT_OUTPUT": str(comment),
        "FAIL_LOOKUP": str(int(scenario == "lookup_failure")),
        "CREATE_ATTEMPT": str(tmp_path / "create-attempt"),
        "OPEN_PRS": (
            '[[{"number":9,"head":{"ref":"unrelated"}}],'
            '[{"number":51,"head":{"ref":"backport/42-to-1.3-123"}}]]'
            if scenario == "existing_pr"
            else "[[]]"
        ),
    }
    result = subprocess.run(
        ["bash", str(ENTRY_POINT), "backport"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    if scenario == "empty":
        assert result.returncode == 0
        assert "empty cherry-pick" in result.stdout
    elif scenario == "conflict":
        assert result.returncode != 0
        assert "failed due to conflicts" in comment.read_text()
        assert "Backport Failed" in summary.read_text()
        assert not (repo / ".git/CHERRY_PICK_HEAD").exists()
    elif scenario == "create_failure":
        assert result.returncode != 0
        assert "Failed to create PR" in result.stdout
        assert git("ls-remote", "--heads", "origin", "backport/*") == ""
    elif scenario == "push_failure":
        assert result.returncode != 0
        assert "Failed to push" in result.stdout
        assert git("ls-remote", "--heads", "origin", "backport/*") == ""
    elif scenario == "missing_branch":
        assert result.returncode != 0
        assert "does not exist" in result.stdout
    elif scenario == "lookup_failure":
        assert result.returncode != 0
        assert not (tmp_path / "create-attempt").exists()
        assert git("branch", "--list", "backport/*") == ""
    elif scenario == "existing_pr":
        assert result.returncode == 0
        assert "already exists: #51" in comment.read_text()
        assert not (tmp_path / "create-attempt").exists()
    elif scenario == "merge_commit":
        assert result.returncode != 0
        assert "empty cherry-pick" not in result.stdout
        assert not (tmp_path / "create-attempt").exists()
    else:
        assert result.returncode != 0
        assert "Invalid branch name" in result.stdout
