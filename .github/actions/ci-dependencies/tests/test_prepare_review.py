"""Verify the transition from trusted setup to the pull request sandbox."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PREPARE = ROOT / "ci-dependencies" / "reusable" / "prepare_review.sh"
SYNC = ROOT / "bot-ai-review" / "reusable" / "sync_copy.sh"


@pytest.mark.parametrize(
    ("system_deps", "distro", "configured_django"),
    [
        (False, "", ""),
        (True, "ubuntu test", "django~=6.1"),
        (False, "line1\nline2", ""),
        (True, "a=b", ""),
        (False, "$(false)", ""),
    ],
)
def test_prepares_trusted_code_then_synchronizes_pull_request(
    tmp_path, system_deps, distro, configured_django
):
    base = tmp_path / "base"
    pr = tmp_path / "pr"
    run = tmp_path / "run"
    home = tmp_path / "reviewer"
    runner_home = tmp_path / "runner"
    tool_cache = tmp_path / "tool-cache"
    runner_temp = tmp_path / "runner-temp"
    bins = tmp_path / "bin"
    for directory in (base, pr, run, home, runner_home, tool_cache, runner_temp, bins):
        directory.mkdir()
    pip_cache = runner_home / ".cache" / "pip"
    pip_cache.mkdir(parents=True)
    (pip_cache / "package").write_text("pip cache")
    extra_cache = runner_home / ".cache" / "ci-deps"
    extra_cache.mkdir()
    (extra_cache / "package").write_text("other cache")
    yarn_cache = tmp_path / "yarn" / "v6"
    yarn_cache.mkdir(parents=True)
    (yarn_cache / "package").write_text("yarn cache")
    (base / "feature.py").write_text("base")
    (base / "deleted.py").write_text("delete me")
    (base / "install-ci-deps.sh").write_text(
        '#!/bin/bash\nif [ "${CI_SYSTEM_DEPS_ONLY:-0}" = 1 ]; then\n'
        '  printf "%s:%s:%s:%s:%s" "$(cat feature.py)" "${SECRET_SENTINEL-unset}" '
        '"${CI-unset}" "${DISTRO-unset}" "${DJANGO_VERSION-unset}" > system.txt\n'
        'else\n  printf "%s:%s:%s:%s:%s:%s:%s" "$(cat feature.py)" '
        '"${SECRET_SENTINEL-unset}" "${CI_QA-unset}" '
        '"${CI_SYSTEM_DEPS_READY:-0}" "${CI-unset}" "${DISTRO-unset}" '
        '"${DJANGO_VERSION-unset}" > installed.txt\nfi\n'
    )
    (pr / "feature.py").write_text("pull request")
    sudo = bins / "sudo"
    sudo.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['-u', 'reviewer']: args = args[2:]\n"
        "if args[:4] == ['-n', '-H', '-u', 'reviewer']: args = args[4:]\n"
        "if args[:3] == ['-n', '-u', 'reviewer']:\n"
        "    args = args[3:]\n"
        "    if args[0] == 'test': sys.exit(1)\n"
        "    if args[0] == 'find': sys.exit(0)\n"
        "if args[0] == 'find' and '-user' in args: sys.exit(0)\n"
        "if args[0] == 'chown': sys.exit(0)\n"
        "if args[0] == 'rsync' and not args[-1].startswith("
        "os.path.dirname(os.environ['GITHUB_WORKSPACE'])): sys.exit(7)\n"
        "if args[0] == 'rsync': args.remove('--chown=reviewer:reviewer')\n"
        "if args[0] == 'install': args = [a for a in args if a not in "
        "('-o', '-g', 'reviewer')]\n"
        "os.execvp(args[0], args)\n"
    )
    sudo.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bins}:/usr/bin:/bin",
        "HOME": str(runner_home),
        "GITHUB_WORKSPACE": str(base),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "RUNNER_TOOL_CACHE": str(tool_cache),
        "RUNNER_TEMP": str(runner_temp),
        "YARN_CACHE_DIR": str(yarn_cache),
        "CI_QA": "1",
        "CI": "true",
        "INSTALLER_ENV": json.dumps(
            {"DISTRO": distro, "DJANGO_VERSION": "django~=5.2"}
        ),
        "DJANGO_VERSION": configured_django,
        "SYSTEM_DEPS_ENABLED": str(system_deps).lower(),
        "SECRET_SENTINEL": "private",
    }
    subprocess.run(
        ["bash", str(PREPARE), str(run), str(home)],
        env=env,
        check=True,
        capture_output=True,
    )
    outputs = (tmp_path / "output").read_text().splitlines()
    assert f"safe_path={bins}:/usr/bin:/bin" in outputs
    assert f"sandbox_path={bins}:/usr/bin:/bin" in outputs
    django_version = configured_django or "django~=5.2"
    assert (
        run / "installed.txt"
    ).read_text() == f"base:unset:1:{int(system_deps)}:true:{distro}:{django_version}"
    if system_deps:
        assert (
            base / "system.txt"
        ).read_text() == f"base:unset:true:{distro}:{django_version}"
    assert (home / ".cache" / "pip" / "package").read_text() == "pip cache"
    assert (home / ".cache" / "ci-deps" / "package").read_text() == "other cache"
    assert (home / ".cache" / "yarn" / "v6" / "package").read_text() == "yarn cache"
    subprocess.run(
        [str(SYNC), str(pr), str(run), str(home / ".ai-review-files")],
        check=True,
        capture_output=True,
    )
    assert (run / "feature.py").read_text() == "pull request"
    assert not (run / "deleted.py").exists()
    assert (
        run / "installed.txt"
    ).read_text() == f"base:unset:1:{int(system_deps)}:true:{distro}:{django_version}"


@pytest.mark.parametrize(
    "installer_env",
    ["{", "[]", "null", '{"BAD-NAME":"x"}', '{"X":1}', '{"X":"\\u0000"}'],
)
def test_rejects_invalid_installer_environment_before_setup(tmp_path, installer_env):
    result = subprocess.run(
        ["bash", str(PREPARE)],
        env={
            **os.environ,
            "INSTALLER_ENV": installer_env,
            "GITHUB_WORKSPACE": str(tmp_path),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not (tmp_path / "installed.txt").exists()
