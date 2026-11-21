"""Verify assignment bot command selection and failure exit codes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ACTION_DIR = Path(__file__).resolve().parents[1]
REUSABLE = ACTION_DIR / "reusable"


def test_unknown_bot_command_fails():
    workflow = ACTION_DIR.parents[1] / "workflows/reusable-bot-autoassign.yml"
    steps = yaml.safe_load(workflow.read_text())["jobs"]["run-bot"]["steps"]
    command = next(
        step["run"] for step in steps if step["name"] == "Execute bot script"
    )
    result = subprocess.run(
        ["bash", "-c", command],
        env=os.environ | {"BOT_COMMAND": "unknown", "GITHUB_EVENT_PATH": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Unknown bot type: unknown" in result.stdout


def test_rejects_empty_validation_repository_list():
    result = subprocess.run(
        [sys.executable, str(REUSABLE / "validation_repositories.py")],
        env=os.environ | {"PUBLIC_VALIDATION_REPOSITORIES": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "prevent minting a token with org-wide access" in result.stdout


def test_accepts_nonempty_validation_repository_list():
    result = subprocess.run(
        [sys.executable, str(REUSABLE / "validation_repositories.py")],
        env=os.environ | {"PUBLIC_VALIDATION_REPOSITORIES": "openwisp/example"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


@pytest.mark.parametrize(
    ("bot", "diagnostic"),
    [
        ("issue_assignment", "GitHub client not properly initialized"),
        ("pr_reopen", "Usage: python pr_reopen_bot.py"),
        ("stale_pr", "GitHub client not properly initialized"),
    ],
)
def test_bot_failure_returns_nonzero(bot, diagnostic):
    env = os.environ.copy()
    for name in ("GITHUB_TOKEN", "VALIDATION_GITHUB_TOKEN", "REPOSITORY"):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, str(REUSABLE / f"{bot}_bot.py")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, result.stderr
    assert diagnostic in result.stdout, result.stderr


@pytest.mark.parametrize("repositories", [" ", ",\n , "])
def test_rejects_validation_list_without_repository_entries(repositories):
    result = subprocess.run(
        [sys.executable, str(REUSABLE / "validation_repositories.py")],
        env=os.environ | {"PUBLIC_VALIDATION_REPOSITORIES": repositories},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "prevent minting a token with org-wide access" in result.stdout
