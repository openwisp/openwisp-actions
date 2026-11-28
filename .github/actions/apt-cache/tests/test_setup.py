"""Check APT cache setup without changing the host configuration."""

import subprocess
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "setup.sh"


def test_configures_cache_outside_apt_cleanup_directory(tmp_path):
    sudo = tmp_path / "sudo"
    sudo.write_text(
        '#!/bin/sh\n[ "$1" = tee ] && [ "$2" = /etc/apt/apt.conf.d/99-openwisp-cache ] || exit 1\n'
        'tee "$TEST_OUTPUT"\n'
    )
    sudo.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    output = tmp_path / "apt.conf"
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={
            "PATH": f"{tmp_path}:/usr/bin:/bin",
            "HOME": str(home),
            "TEST_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (home / ".cache/apt-ci/archives/partial").is_dir()
    config = output.read_text()
    assert f'Dir::Cache::archives "{home}/.cache/apt-ci/archives/";' in config
    assert 'Keep-Downloaded-Packages "true"' in config


def test_only_ci_can_save_cached_archives():
    action = yaml.safe_load((SCRIPT.parent / "action.yml").read_text())
    steps = {step["name"]: step for step in action["runs"]["steps"]}
    write = steps["Restore or save APT archives"]
    restore = steps["Restore APT archives for review"]
    assert write["if"] == "inputs.mode == 'write'"
    assert restore["if"] == "inputs.mode == 'restore'"
    assert restore["uses"].startswith("actions/cache/restore@")
    assert write["with"]["path"] == restore["with"]["path"]
    assert write["with"]["key"] == restore["with"]["key"]


def test_rejects_paths_that_cannot_be_written_to_apt_configuration(tmp_path):
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / 'bad"path')},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Invalid APT cache path" in result.stderr
