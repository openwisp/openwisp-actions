"""Exercise CI failure workflow operations without contacting GitHub."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ACTION_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def runner(tmp_path):
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['CALLS'], 'a') as calls:\n"
        "    calls.write(json.dumps([os.environ.get('GH_TOKEN'), *sys.argv[1:]]) + '\\n')\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['pr', 'view'] and '--json' in args:\n"
        "    if os.environ.get('VIEW_FAIL') == '1':\n"
        "        sys.exit(1)\n"
        "    print(os.environ.get('VIEW_RESPONSE', ''))\n"
        "elif args and args[0] == 'api':\n"
        "    if os.environ.get('API_FAIL') == '1':\n"
        "        sys.exit(1)\n"
        "    if '--allow-escape-sequences' in args:\n"
        "        print(os.environ.get('LOG_RESPONSE', ''))\n"
        "    elif '--method' in args and 'OPEN_PRS' in os.environ:\n"
        "        print(os.environ['OPEN_PRS'])\n"
        "    else:\n"
        "        print(os.environ.get('API_RESPONSE', ''))\n"
    )
    gh.chmod(0o755)
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "CALLS": str(tmp_path / "calls"),
        "GH_TOKEN": "reader",
        "GH_APP_TOKEN": "app",
        "BASE_SHA": "",
        "HEAD_SHA": "head",
        "PR_NUM": "42",
        "REPO": "example/repo",
        "RUN_ID": "123",
        "GITHUB_OUTPUT": str(tmp_path / "output"),
    }

    def run(operation, **values):
        directory = "caller" if operation == "find-pr" else "reusable"
        result = subprocess.run(
            ["bash", str(ACTION_DIR / directory / f"{operation}.sh")],
            cwd=tmp_path,
            env=env | values,
            capture_output=True,
            text=True,
        )
        calls_path = tmp_path / "calls"
        calls = []
        if calls_path.exists():
            calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
        return result, calls

    return tmp_path, run


def test_diff_falls_back_to_app_token_for_base(runner):
    directory, run = runner
    result, calls = run("fetch-diff", VIEW_RESPONSE="base", API_RESPONSE="diff data")
    assert result.returncode == 0
    assert (directory / "pr.diff").read_text() == "diff data\n"
    assert calls[0][0:3] == ["app", "pr", "view"]
    assert calls[1][0] == "reader"
    assert "repos/example/repo/compare/base...head" in calls[1]


def test_failed_diff_is_discarded(runner):
    directory, run = runner
    result, _ = run("fetch-diff", BASE_SHA="base", API_FAIL="1")
    assert result.returncode == 0
    assert (directory / "pr.diff").read_text() == ""
    assert "Could not fetch the PR diff" in result.stdout


def test_missing_failed_jobs_produces_fallback(runner):
    directory, run = runner
    result, _ = run("fetch-logs", API_FAIL="1")
    assert result.returncode == 0
    assert (directory / "failed_logs.txt").read_text() == (
        "Could not fetch failed jobs for run 123.\n"
    )


def test_fetch_logs_extracts_failure_sections(runner):
    directory, run = runner
    logs = "before\n##[group]test\nfirst line\n##[error]failed\nafter"
    result, calls = run("fetch-logs", API_RESPONSE="17", LOG_RESPONSE=logs)
    assert result.returncode == 0
    extracted = (directory / "failed_logs.txt").read_text()
    assert "===== JOB 17 =====" in extracted
    assert "##[group]test\nfirst line\n##[error]failed" in extracted
    assert "after" not in extracted
    assert "--allow-escape-sequences" in calls[1]


@pytest.mark.parametrize("previous", [0, 3])
def test_retry_respects_per_commit_limit(runner, previous):
    directory, run = runner
    marker = "<!-- ci-transient-retry head -->"
    result, calls = run("retry", VIEW_RESPONSE="\n".join([marker] * previous))
    assert result.returncode == 0
    output = (directory / "output").read_text()
    assert output == f"retried={'true' if previous == 0 else 'false'}\n"
    retry_calls = [call for call in calls if "-X" in call]
    assert len(retry_calls) == (1 if previous == 0 else 0)


def test_post_comment_requires_failed_logs(runner):
    directory, run = runner
    (directory / "solution.md").write_text("Suggested fix")
    (directory / "failed_logs.txt").write_text("No failed jobs found.\n")
    result, _ = run("post-comment")
    assert result.returncode == 0
    assert "No CI failures detected" in result.stdout


def test_find_pr_uses_payload_and_resolves_author(runner):
    directory, run = runner
    result, calls = run(
        "find-pr",
        PR_NUMBER_PAYLOAD="42",
        EVENT_HEAD_SHA="abc",
        EVENT_HEAD_REPOSITORY="example/fork",
        EVENT_HEAD_BRANCH="feature",
        VIEW_RESPONSE="contributor",
    )
    assert result.returncode == 0
    assert (directory / "output").read_text() == "number=42\nauthor=contributor\n"
    assert calls[0][1:4] == ["pr", "view", "42"]


@pytest.mark.parametrize("commits_match", [True, False])
def test_find_pr_matches_head_in_commit_or_open_pr_lookup(runner, commits_match):
    directory, run = runner
    prs = json.dumps(
        [
            {
                "state": "open",
                "number": 42,
                "head": {
                    "sha": "abc",
                    "repo": {"full_name": "example/fork"},
                    "ref": "feature",
                },
            }
        ]
    )
    result, calls = run(
        "find-pr",
        PR_NUMBER_PAYLOAD="",
        EVENT_HEAD_SHA="abc",
        EVENT_HEAD_REPOSITORY="example/fork",
        EVENT_HEAD_BRANCH="feature",
        API_RESPONSE=prs if commits_match else "[]",
        OPEN_PRS=prs,
        VIEW_RESPONSE="contributor",
    )
    assert result.returncode == 0
    assert (directory / "output").read_text() == "number=42\nauthor=contributor\n"
    open_lookups = [call for call in calls if "--method" in call]
    if commits_match:
        assert not open_lookups
    else:
        assert len(open_lookups) == 1
        assert "head=example:feature" in open_lookups[0]


def test_find_pr_rejects_mismatched_fork(runner):
    directory, run = runner
    prs = json.dumps(
        [
            {
                "state": "open",
                "number": 42,
                "head": {
                    "sha": "abc",
                    "repo": {"full_name": "other/fork"},
                    "ref": "feature",
                },
            }
        ]
    )
    result, calls = run(
        "find-pr",
        PR_NUMBER_PAYLOAD="",
        EVENT_HEAD_SHA="abc",
        EVENT_HEAD_REPOSITORY="example/fork",
        EVENT_HEAD_BRANCH="feature",
        API_RESPONSE=prs,
    )
    assert result.returncode == 0
    assert "No open PR found" in result.stdout
    assert not (directory / "output").exists()
    assert len(calls) == 2


def test_retry_skips_when_previous_count_is_unavailable(runner):
    directory, run = runner
    result, calls = run("retry", VIEW_FAIL="1")
    assert result.returncode == 0
    assert (directory / "output").read_text() == "retried=false\n"
    assert not any("-X" in call for call in calls)
