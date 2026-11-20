"""Exercise version branch operations in local repositories."""

import os
import subprocess
from pathlib import Path

import pytest

ENTRY_POINT = Path(__file__).resolve().parents[1] / "scripts/__main__.sh"


def test_get_version_from_caller_directory(tmp_path):
    (tmp_path / "sample.py").write_text('VERSION = (1, 23, 4, "dev")\n')
    output = tmp_path / "output"
    env = os.environ | {"MODULE_NAME": "sample", "GITHUB_OUTPUT": str(output)}
    subprocess.run(
        ["bash", str(ENTRY_POINT), "version"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert output.read_text() == "version=1.23\n"


@pytest.mark.parametrize("scenario", ["missing", "fast_forward", "diverged"])
def test_replicate_version_branch(tmp_path, scenario):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-b", "master")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    (repo / "file").write_text("base\n")
    git("add", "file")
    git("commit", "-m", "Initial")
    git("init", "--bare", str(tmp_path / "remote.git"))
    git("remote", "add", "origin", str(tmp_path / "remote.git"))
    git("branch", "1.2")
    if scenario == "diverged":
        git("checkout", "1.2")
        (repo / "other").write_text("divergent\n")
        git("add", "other")
        git("commit", "-m", "Different")
        git("checkout", "master")
    if scenario != "missing":
        git("push", "origin", "1.2")
    else:
        git("branch", "-D", "1.2")
    (repo / "file").write_text("new\n")
    git("commit", "-am", "New")
    sha = git("rev-parse", "HEAD")
    env = os.environ | {"VERSION": "1.2", "GITHUB_SHA": sha}
    result = subprocess.run(
        ["bash", str(ENTRY_POINT), "replicate"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    if scenario == "diverged":
        assert result.returncode != 0
        assert "has diverged" in result.stderr
        assert git("rev-parse", "1.2") != sha
    else:
        assert result.returncode == 0, result.stderr
        assert git("rev-parse", "1.2") == sha
