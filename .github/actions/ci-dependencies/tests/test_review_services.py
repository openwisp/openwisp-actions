"""Verify review services use trusted Compose files and a restricted environment."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "reusable" / "review_services.sh"


def prepare_repo(tmp_path, services):
    repo = tmp_path / "repo"
    repo.mkdir()
    workflow = repo / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        f'jobs:\n  test:\n    env:\n      AI_REVIEW_SERVICES: "{services}"\n'
    )
    (repo / "docker-compose.yml").write_text("services:\n  redis:\n    image: redis\n")
    git = [
        "git",
        "-C",
        str(repo),
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
    ]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "Trusted"], check=True)
    sha = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    # The default commit, not the target branch, controls privileged setup.
    workflow.write_text(
        'jobs:\n  test:\n    env:\n      AI_REVIEW_SERVICES: "unexpected"\n'
    )
    (repo / "docker-compose.yml").write_text("untrusted working tree\n")
    subprocess.run([*git, "commit", "-qam", "Target"], check=True)
    bins = tmp_path / "bin"
    bins.mkdir()
    docker = bins / "docker"
    docker.write_text(
        '#!/bin/sh\nprintf "%s|%s|%s\\n" "$PWD" "$*" '
        '"${SECRET_SENTINEL-unset}" >> "$HOME/docker-calls"\n'
        'case "$*" in *" up "*) [ ! -f "$HOME/fail-up" ] || exit 7 ;; esac\n'
    )
    docker.chmod(0o755)
    output = tmp_path / "output"
    env = {
        **os.environ,
        "PATH": f"{bins}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "GITHUB_WORKSPACE": str(repo),
        "GITHUB_OUTPUT": str(output),
        "RUNNER_TEMP": str(tmp_path),
        "DEFAULT_SHA": sha,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "SECRET_SENTINEL": "private",
    }
    return repo, output, env


def test_starts_and_removes_only_trusted_services(tmp_path):
    repo, output, env = prepare_repo(tmp_path, "redis,influxdb")
    result = subprocess.run(
        ["bash", str(SCRIPT), "start"], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    directory = Path(values["directory"])
    assert directory != repo
    assert (directory / "docker-compose.yml").read_text() == (
        "services:\n  redis:\n    image: redis\n"
    )
    calls = (tmp_path / "docker-calls").read_text().splitlines()
    assert calls == [
        f"{directory}|compose -p ai-review-123-2 up -d --no-build --no-deps redis influxdb|unset"
    ]
    result = subprocess.run(
        ["bash", str(SCRIPT), "stop", str(directory), values["project"]],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not directory.exists()
    assert (tmp_path / "docker-calls").read_text().splitlines()[-1] == (
        f"{directory}|compose -p ai-review-123-2 down --volumes --remove-orphans|unset"
    )


@pytest.mark.parametrize("services", ["", "redis;touch-bad", "redis,postgres"])
def test_skips_unconfigured_and_rejects_unknown_services(tmp_path, services):
    _, _, env = prepare_repo(tmp_path, services)
    result = subprocess.run(
        ["bash", str(SCRIPT), "start"], env=env, capture_output=True, text=True
    )
    assert result.returncode == (0 if not services else 1)
    assert not (tmp_path / "docker-calls").exists()


def test_cleanup_remains_possible_after_a_failed_start(tmp_path):
    _, output, env = prepare_repo(tmp_path, "redis")
    (tmp_path / "fail-up").touch()
    result = subprocess.run(
        ["bash", str(SCRIPT), "start"], env=env, capture_output=True, text=True
    )
    assert result.returncode == 7
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    result = subprocess.run(
        ["bash", str(SCRIPT), "stop", values["directory"], values["project"]],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not Path(values["directory"]).exists()
