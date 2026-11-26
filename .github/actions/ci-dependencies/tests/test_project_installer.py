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
        "prettier@3.9.4",
    ]
    if github_actions:
        assert github_path.read_text().splitlines() == [str(home / ".local" / "bin")]
    else:
        assert not github_path.exists()
