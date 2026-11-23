"""Check review selection against actual CI workflow files."""

import os
import subprocess
from pathlib import Path

import pytest

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
        "node_version=",
        "chrome=false",
        "firefox=false",
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
        "node_version=",
        "chrome=false",
        "firefox=false",
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


@pytest.mark.parametrize(
    ("browsers", "chrome", "firefox"),
    [
        ("none", "false", "false"),
        ("chrome", "true", "false"),
        ("firefox", "false", "true"),
        ("chrome,firefox", "true", "true"),
    ],
)
def test_selects_explicit_browsers_for_python(tmp_path, browsers, chrome, firefox):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    env:\n"
        f'      AI_REVIEW_BROWSERS: "{browsers}"\n'
        "    steps:\n      - uses: actions/setup-python@abcdef\n"
        '        with:\n          python-version: "3.12"\n'
    )
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "GITHUB_OUTPUT": str(output), "CI_ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert f"chrome={chrome}" in output.read_text().splitlines()
    assert f"firefox={firefox}" in output.read_text().splitlines()


def test_legacy_ci_chrome_action_selects_chrome(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    steps:\n"
        "      - uses: actions/setup-python@abcdef\n"
        '        with:\n          python-version: "3.12"\n'
        "      - uses: browser-actions/setup-chrome@abcdef\n"
    )
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "GITHUB_OUTPUT": str(output), "CI_ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "chrome=true" in output.read_text().splitlines()


def test_distro_matrix_uses_static_python_and_node_versions(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    strategy:\n      matrix:\n"
        '        distro: ["debian", "ubuntu"]\n'
        '        include:\n          - distro: "ubuntu"\n'
        "            review_default: true\n"
        "    steps:\n      - uses: actions/setup-python@abcdef\n"
        '        with:\n          python-version: "3.12"\n'
        "      - uses: actions/setup-node@abcdef\n"
        '        with:\n          node-version: "22"\n'
    )
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "GITHUB_OUTPUT": str(output), "CI_ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "python_version=3.12" in output.read_text().splitlines()
    assert "node_version=22" in output.read_text().splitlines()


def test_rejects_unknown_browser(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        'jobs:\n  test:\n    env:\n      AI_REVIEW_BROWSERS: "other"\n'
        "    steps:\n      - uses: actions/setup-python@abcdef\n"
        '        with:\n          python-version: "3.12"\n'
    )
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={
            **os.environ,
            "GITHUB_OUTPUT": str(tmp_path / "output"),
            "CI_ROOT": str(tmp_path),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "browser" in result.stderr.lower()
