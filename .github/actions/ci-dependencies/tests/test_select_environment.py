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
        "extra_cache_glob=",
        "extra_cache_variant=",
        "system_deps=false",
        "installer_env={}",
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
        "extra_cache_glob=",
        "extra_cache_variant=",
        "system_deps=false",
        "installer_env={}",
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


def test_reads_optional_dependency_cache_glob(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        'jobs:\n  test:\n    env:\n      AI_REVIEW_CACHE_GLOB: "**/requirements*.txt"\n'
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
    assert "extra_cache_glob=**/requirements*.txt" in output.read_text().splitlines()


def test_rejects_unsafe_dependency_cache_glob(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        'jobs:\n  test:\n    env:\n      AI_REVIEW_CACHE_GLOB: "../../other"\n'
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
    assert "cache" in result.stderr.lower()


def test_cache_variant_uses_the_selected_matrix_axes(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        'jobs:\n  test:\n    env:\n      AI_REVIEW_CACHE_GLOB: "requirements*.txt"\n'
        '      AI_REVIEW_CACHE_AXES: "distro,target"\n'
        '    strategy:\n      matrix:\n        distro: ["debian", "ubuntu"]\n'
        '        target: ["arm"]\n        include:\n          - distro: "ubuntu"\n'
        '            target: "arm"\n            review_default: true\n'
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
    assert "extra_cache_variant=ubuntu:arm" in output.read_text().splitlines()


def test_cache_variant_supports_false_matrix_values(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        'jobs:\n  test:\n    env:\n      AI_REVIEW_CACHE_GLOB: "requirements*.txt"\n'
        '      AI_REVIEW_CACHE_AXES: "feature"\n'
        "    strategy:\n      matrix:\n        feature: [false]\n"
        "        include:\n          - feature: false\n            review_default: true\n"
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
    assert "extra_cache_variant=false" in output.read_text().splitlines()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", "true"), ("false", "false"), ('"true"', "true")],
)
def test_reads_system_dependency_setting(tmp_path, value, expected):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        f"jobs:\n  test:\n    env:\n      AI_REVIEW_SYSTEM_DEPS: {value}\n"
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
    assert f"system_deps={expected}" in output.read_text().splitlines()


def test_rejects_invalid_system_dependency_setting(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    env:\n      AI_REVIEW_SYSTEM_DEPS: invalid\n"
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
    assert "Invalid AI_REVIEW_SYSTEM_DEPS" in result.stderr


def test_selects_matrix_environment_for_installer(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  test:\n    strategy:\n      matrix:\n"
        '        distro: ["debian", "ubuntu"]\n'
        '        include:\n          - distro: "ubuntu"\n'
        "            review_default: true\n"
        "    steps:\n      - uses: actions/setup-python@abcdef\n"
        '        with:\n          python-version: "3.12"\n'
        "      - id: deps\n        env:\n"
        '          DISTRO: "${{ matrix.distro }}"\n'
        '          SECRET: "${{ secrets.TOKEN }}"\n'
    )
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "GITHUB_OUTPUT": str(output), "CI_ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert 'installer_env={"DISTRO":"ubuntu"}' in output.read_text().splitlines()
