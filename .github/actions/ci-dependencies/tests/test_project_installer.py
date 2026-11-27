"""Check the dependency installer used by openwisp-actions CI and AI reviews."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("github_actions", [False, True])
def test_installs_python_and_prettier_dependencies(tmp_path, github_actions):
    for tool in ("python", "npm"):
        stub = tmp_path / tool
        stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "{tool}" "$@"\n')
        stub.chmod(0o755)
    home = tmp_path / "review home"
    home.mkdir()
    github_path = tmp_path / "path"
    env = {**os.environ, "HOME": str(home), "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    env.pop("GITHUB_PATH", None)
    if github_actions:
        env["GITHUB_PATH"] = str(github_path)
    result = subprocess.run(
        ["./install-ci-deps.sh"], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "python\n-m\npip\ninstall\n-r\nrequirements-test.txt\n" in result.stdout
    assert result.stdout.splitlines()[-7:] == [
        "npm",
        "install",
        "--global",
        "--ignore-scripts",
        "--prefix",
        str(home / ".local"),
        "prettier",
    ]
    if github_actions:
        assert github_path.read_text().splitlines() == [str(home / ".local" / "bin")]
    else:
        assert not github_path.exists()


@pytest.mark.parametrize("failure", ["python", "npm"])
def test_stops_when_dependency_installation_fails(tmp_path, failure):
    marker = tmp_path / "npm-ran"
    for tool in ("python", "npm", "sleep"):
        stub = tmp_path / tool
        commands = []
        if tool == "npm":
            commands.append(f'touch "{marker}"')
        commands.append("exit 1" if tool == failure else "exit 0")
        stub.write_text("#!/bin/sh\n" + "\n".join(commands) + "\n")
        stub.chmod(0o755)
    github_path = tmp_path / "path"
    github_path.write_text("existing\n")
    result = subprocess.run(
        ["./install-ci-deps.sh"],
        cwd=ROOT,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "GITHUB_PATH": str(github_path),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert marker.exists() == (failure == "npm")
    assert github_path.read_text() == "existing\n"
