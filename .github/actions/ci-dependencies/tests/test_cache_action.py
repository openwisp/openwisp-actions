"""Check that CI and review calculate the same dependency-cache key."""

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / "ci-cache" / "action.yml"


def cache_key(tmp_path, mode, dependency_hash, **variables):
    action = yaml.safe_load(ACTION.read_text())
    script = action["runs"]["steps"][0]["run"]
    output = tmp_path / f"{mode}-{dependency_hash}"
    env = {
        **os.environ,
        "MODE": mode,
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
        "IMAGE_OS": "ubuntu24",
        "PYTHON_VERSION": "3.13.2",
        "NODE_VERSION": "22.1.0",
        "DJANGO_VERSION": "django~=6.0.0",
        "VARIANT": "ubuntu:arm",
        "DEPS_HASH": dependency_hash,
        "GITHUB_OUTPUT": str(output),
        **variables,
    }
    result = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True
    )
    return result, output.read_text() if output.exists() else ""


def test_ci_and_review_share_key_and_dependency_changes_invalidate_it(tmp_path):
    ci, ci_key = cache_key(tmp_path, "write", "old-hash")
    review, review_key = cache_key(tmp_path, "restore", "old-hash")
    changed, changed_key = cache_key(tmp_path, "restore", "new-hash")
    assert ci.returncode == review.returncode == changed.returncode == 0
    assert ci_key == review_key
    assert ci_key != changed_key


def test_rejects_invalid_mode(tmp_path):
    result, output = cache_key(tmp_path, "invalid", "hash")
    assert result.returncode != 0
    assert "invalid" in result.stderr.lower()
    assert not output


def test_runtime_boundaries_do_not_collide(tmp_path):
    _, first = cache_key(
        tmp_path, "write", "hash", PYTHON_VERSION="1-2", NODE_VERSION="3"
    )
    _, second = cache_key(
        tmp_path, "restore", "hash", PYTHON_VERSION="1", NODE_VERSION="2-3"
    )
    assert first != second


def test_cache_hash_excludes_the_reusable_workflow_checkout():
    action = yaml.safe_load(ACTION.read_text())
    expression = action["runs"]["steps"][0]["env"]["DEPS_HASH"]
    assert "!openwisp-actions/**" in expression
