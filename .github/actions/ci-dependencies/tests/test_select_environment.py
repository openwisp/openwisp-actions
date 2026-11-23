"""Check review selection against actual CI workflow files."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "reusable" / "select_environment.sh"


def test_selects_python_and_django_from_workflow(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    strategy:\n      matrix:\n"
        '        python-version: ["3.12", "3.13"]\n'
        '        django-version: ["django~=6.1.0"]\n'
        '        include:\n          - python-version: "3.13"\n'
        '            django-version: "django~=6.1.0"\n'
        "            review_default: true\n"
    )
    output = tmp_path / "output"
    env = {**os.environ, "GITHUB_OUTPUT": str(output), "CI_ROOT": str(tmp_path)}
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text().splitlines() == [
        "python_version=3.13",
        "django_version=django~=6.1.0",
        "node_version_file=",
    ]


def test_selects_python_from_non_matrix_workflow(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    steps:\n"
        "      - uses: actions/setup-python@abcdef\n"
        '        with:\n          python-version: "3.12"\n'
    )
    output = tmp_path / "output"
    env = {**os.environ, "GITHUB_OUTPUT": str(output), "CI_ROOT": str(tmp_path)}
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text().splitlines() == [
        "python_version=3.12",
        "django_version=",
        "node_version_file=",
    ]


def test_override_selects_another_valid_python_row(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    strategy:\n      matrix:\n"
        '        python-version: ["3.12", "3.13"]\n'
        '        include:\n          - python-version: "3.13"\n'
        "            review_default: true\n"
    )
    output = tmp_path / "output"
    env = {
        **os.environ,
        "GITHUB_OUTPUT": str(output),
        "CI_ROOT": str(tmp_path),
        "REVIEW_MATRIX_OVERRIDE": '{"python-version": "3.12"}',
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text().splitlines()[0] == "python_version=3.12"


def test_rejects_unrecognized_runtime(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    strategy:\n      matrix:\n"
        "        include:\n          - build-type: dev\n"
        "            review_default: true\n"
    )
    output = tmp_path / "output"
    env = {**os.environ, "GITHUB_OUTPUT": str(output), "CI_ROOT": str(tmp_path)}
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "runtime" in result.stderr
