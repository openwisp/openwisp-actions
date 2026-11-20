"""Test changelog runner validation against local artifacts and stubbed APIs."""

import json
import os
import subprocess
from pathlib import Path

import pytest

CALLER = Path(__file__).resolve().parents[1] / "caller"


@pytest.fixture
def runner(tmp_path):
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "pr_number").write_text("42\n")
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "if any('/reviews?' in arg for arg in sys.argv):\n"
        "    print(os.environ['REVIEWS'])\n"
        "elif any('/compare/' in arg for arg in sys.argv):\n"
        "    if '-H' in sys.argv and os.environ.get('DIFF_FAIL') == '1':\n"
        "        sys.exit(1)\n"
        "    print(os.environ['DIFF'] if '-H' in sys.argv else os.environ['COMPARISON'])\n"
        "else:\n"
        "    print(os.environ['PR'])\n"
    )
    gh.chmod(0o755)
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "ARTIFACT_DIR": str(artifact),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "REPOSITORY": "example/repo",
        "PR_NUMBER": "42",
        "EXPECTED_HEAD_SHA": "abc",
        "PR": json.dumps(
            {
                "head": {"sha": "abc"},
                "base": {"sha": "base", "repo": {"full_name": "example/repo"}},
            }
        ),
        "REVIEWS": json.dumps(
            [
                [
                    {
                        "user": {"id": 1},
                        "state": "APPROVED",
                        "commit_id": "abc",
                        "author_association": "MEMBER",
                        "submitted_at": "2026-01-01",
                        "id": 1,
                    }
                ]
            ]
        ),
    }

    def run(operation, **values):
        return subprocess.run(
            ["bash", str(CALLER / f"{operation}.sh")],
            cwd=tmp_path,
            env=env | values,
            capture_output=True,
            text=True,
        )

    return tmp_path, artifact, run


def test_metadata_reads_regular_pr_number(runner):
    root, _, run = runner
    result = run("read-metadata")
    assert result.returncode == 0
    assert (root / "output").read_text() == "pr_number=42\n"


@pytest.mark.parametrize("invalid", ["extra", "symlink", "oversized", "nonnumeric"])
def test_metadata_rejects_untrusted_artifact_shapes(runner, invalid):
    root, artifact, run = runner
    number = artifact / "pr_number"
    if invalid == "extra":
        (artifact / "extra").write_text("extra")
    elif invalid == "symlink":
        number.unlink()
        number.symlink_to(root / "elsewhere")
    elif invalid == "oversized":
        number.write_text("1" * 17)
    else:
        number.write_text("42\nother")
    result = run("read-metadata")
    assert result.returncode != 0
    assert not (root / "output").exists()


def test_approval_requires_matching_current_head(runner):
    root, _, run = runner
    result = run("verify-approval")
    assert result.returncode == 0
    assert (root / "output").read_text() == "head_sha=abc\nbase_sha=base\n"
    result = run("verify-approval", EXPECTED_HEAD_SHA="old")
    assert result.returncode != 0
    assert "head changed" in result.stdout


def test_approval_rejects_review_for_old_commit(runner):
    _, _, run = runner
    reviews = [
        [
            {
                "user": {"id": 1},
                "state": "APPROVED",
                "commit_id": "old",
                "author_association": "MEMBER",
                "id": 1,
            }
        ]
    ]
    result = run("verify-approval", REVIEWS=json.dumps(reviews))
    assert result.returncode != 0
    assert "no current eligible approval" in result.stdout


def test_association_rejects_changed_head_or_repository(runner):
    root, _, run = runner
    result = run("verify-association")
    assert result.returncode == 0
    assert (root / "output").read_text() == "head_sha=abc\n"
    result = run("verify-association", REPOSITORY="different/repo")
    assert result.returncode != 0
    assert "does not match" in result.stdout


@pytest.mark.parametrize("complete", [True, False])
def test_prepare_diff_requires_complete_comparison(runner, complete):
    root, _, run = runner
    comparison = {
        "total_commits": 1 if complete else 2,
        "commits": [{"sha": "a" * 40, "commit": {"message": "Fix\nDetails"}}],
        "files": [{}],
    }
    result = run(
        "prepare-diff",
        APPROVED_HEAD_SHA="a" * 40,
        APPROVED_BASE_SHA="b" * 40,
        RUNNER_TEMP=str(root),
        COMPARISON=json.dumps(comparison),
        DIFF="diff data",
    )
    if complete:
        assert result.returncode == 0, result.stderr
        assert (root / "changelog-generator.diff").read_text() == "diff data\n"
        assert (root / "changelog-generator.commits").read_text() == "aaaaaaa Fix\n"
        wrapper = subprocess.run(
            [str(root / "git"), "diff"],
            env=os.environ | {"RUNNER_TEMP": str(root)},
            capture_output=True,
            text=True,
            check=True,
        )
        assert wrapper.stdout == "diff data\n"
    else:
        assert result.returncode != 0
        assert "incomplete pull request comparison" in result.stdout
        assert not (root / "git").exists()


def test_prepare_diff_fails_when_diff_fetch_fails(runner):
    root, _, run = runner
    comparison = {"total_commits": 0, "commits": [], "files": []}
    result = run(
        "prepare-diff",
        APPROVED_HEAD_SHA="a" * 40,
        APPROVED_BASE_SHA="b" * 40,
        RUNNER_TEMP=str(root),
        COMPARISON=json.dumps(comparison),
        DIFF_FAIL="1",
    )
    assert result.returncode != 0
    assert not (root / "git").exists()


@pytest.mark.parametrize(
    ("association", "later_review", "allowed"),
    [
        ("MEMBER", "CHANGES_REQUESTED", False),
        ("MEMBER", "DISMISSED", False),
        ("MEMBER", "COMMENTED", True),
        ("CONTRIBUTOR", None, False),
    ],
)
def test_approval_uses_latest_eligible_decision_across_pages(
    runner, association, later_review, allowed
):
    root, _, run = runner
    approval = {
        "user": {"id": 1},
        "state": "APPROVED",
        "commit_id": "abc",
        "author_association": association,
        "submitted_at": "2026-01-01T00:00:00Z",
        "id": 1,
    }
    pages = [[approval]]
    if later_review:
        pages.append(
            [
                approval
                | {
                    "state": later_review,
                    "submitted_at": "2026-01-02T00:00:00Z",
                    "id": 2,
                }
            ]
        )
    result = run("verify-approval", REVIEWS=json.dumps(pages))
    if allowed:
        assert result.returncode == 0, result.stderr
        assert (root / "output").read_text() == "head_sha=abc\nbase_sha=base\n"
    else:
        assert result.returncode != 0
        assert not (root / "output").exists()
