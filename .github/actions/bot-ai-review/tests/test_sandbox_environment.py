"""Check that review commands do not inherit the runner's configuration paths."""

import os
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "reusable" / "sandbox_shell.sh"
PREPARE = SCRIPT.parent / "prepare_sandbox.sh"


def test_sandbox_uses_reviewer_configuration_and_drops_runner_environment(tmp_path):
    sudo = tmp_path / "sudo"
    sudo.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = sys.argv[sys.argv.index('--') + 1:]\n"
        "prefix = args[:args.index('/usr/bin/unshare')]\n"
        "review = args[args.index('--', args.index('review-namespace')) + 1:]\n"
        "command = prefix + review[:review.index('/bin/bash')] + ['/usr/bin/env']\n"
        "os.execv(command[0], command)\n"
    )
    sudo.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "XDG_CONFIG_HOME": "/home/runner/.config",
        "NPM_CONFIG_USERCONFIG": "/home/runner/.npmrc",
        "SECRET_SENTINEL": "private",
        "SE_CHROME": "/opt/chrome/chrome",
        "SE_CHROMEDRIVER": "/opt/chrome/chromedriver",
        "GECKO_BIN": "/usr/bin/firefox",
        "MOLECULE_DISTRO": "ubuntu2404",
    }
    result = subprocess.run(
        [str(SCRIPT), "-c", "true"], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    environment = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert environment["HOME"] == "/home/reviewer"
    assert environment["PATH"] == f"/home/reviewer/.local/bin:{env['PATH']}"
    assert environment["XDG_CONFIG_HOME"] == "/home/reviewer/.config"
    assert environment["CHROME_BIN"] == "/opt/chrome/chrome"
    assert environment["SE_CHROMEDRIVER"] == "/opt/chrome/chromedriver"
    assert environment["GECKO_BIN"] == "/usr/bin/firefox"
    assert environment["SELENIUM_HEADLESS"] == "1"
    assert environment["CI_DEPS_CACHE"] == "/home/reviewer/.cache/ci-deps"
    assert environment["MOLECULE_DISTRO"] == "ubuntu2404"
    assert "NPM_CONFIG_USERCONFIG" not in environment
    assert "SECRET_SENTINEL" not in environment


def test_pip_configuration_allows_virtualenv_installation(tmp_path):
    sudo = tmp_path / "sudo"
    sudo.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "if args[0] in ('useradd', 'install'): sys.exit(0)\n"
        "if args[:2] == ['-u', 'reviewer']: args = args[2:]\n"
        "args = [arg.replace('/home/reviewer', os.environ['TEST_HOME']) for arg in args]\n"
        "os.execvp(args[0], args)\n"
    )
    sudo.chmod(0o755)
    home = tmp_path / "reviewer"
    home.mkdir()
    env = {
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith("PIP_")
        },
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "TEST_HOME": str(home),
    }
    result = subprocess.run(
        ["bash", str(PREPARE)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    venv = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        env=env,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        [
            str(venv / "bin" / "python"),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "pip",
        ],
        env={**env, "PIP_CONFIG_FILE": str(home / ".config" / "pip" / "pip.conf")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_review_commands_use_installer_virtualenv(tmp_path):
    home = tmp_path / "reviewer"
    run = tmp_path / "run"
    pr = tmp_path / "pr"
    for directory in (home, run, pr):
        directory.mkdir()
    venv = run / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)],
        check=True,
        capture_output=True,
    )
    modules = (
        venv
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    (modules / "review_venv_probe.py").write_text("VALUE = 'installed'\n")
    sync = tmp_path / "sync"
    sync.write_text("#!/bin/sh\nexit 0\n")
    sync.chmod(0o755)
    sudo = tmp_path / "sudo"
    sudo.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = ['/usr/bin/env', '-i', *sys.argv[sys.argv.index('review-namespace') + 1:]]\n"
        "args.remove('/dev/shm')\n"
        "args = [arg.replace('/home/reviewer', os.environ['TEST_HOME'])"
        ".replace('/tmp/ai-review/run', os.environ['TEST_RUN'])"
        ".replace('/tmp/ai-review/pr', os.environ['TEST_PR'])"
        ".replace('/usr/local/bin/ai-review-sync', os.environ['TEST_SYNC'])"
        ".replace('/usr/local/lib/ai-review-write-sandbox.py', os.environ['TEST_SANDBOX']) for arg in args]\n"
        "os.execv(args[0], args)\n"
    )
    sudo.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "TEST_HOME": str(home),
        "TEST_RUN": str(run),
        "TEST_PR": str(pr),
        "TEST_SYNC": str(sync),
        "TEST_SANDBOX": str(SCRIPT.with_name("write_sandbox.py")),
    }
    result = subprocess.run(
        [
            str(SCRIPT),
            "-c",
            "python -c 'import review_venv_probe; print(review_venv_probe.VALUE)'",
        ],
        cwd=pr,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "installed"


@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") != "true", reason="needs runner sudo"
)
def test_review_commands_get_private_shared_memory(tmp_path):
    home, run, pr = [tmp_path / name for name in ("reviewer", "run", "pr")]
    for directory in (home, run, pr):
        directory.mkdir()
    shell = tmp_path / "sandbox_shell.sh"
    script = SCRIPT.read_text()
    for original, replacement in (
        ("/home/reviewer", str(home)),
        ("/tmp/ai-review/run", str(run)),
        ("/tmp/ai-review/pr", str(pr)),
        ("/usr/local/bin/ai-review-sync", "/usr/bin/true"),
        (
            "/usr/local/lib/ai-review-write-sandbox.py",
            str(SCRIPT.with_name("write_sandbox.py")),
        ),
        ("-u reviewer", f'-u "#{os.getuid()}"'),
    ):
        script = script.replace(original, replacement)
    shell.write_text(script)
    marker = Path("/dev/shm") / f"review-test-{uuid.uuid4().hex}"
    probe = (
        "import multiprocessing; from pathlib import Path; "
        f"s = multiprocessing.Semaphore(1); assert s.acquire(); Path({str(marker)!r}).touch()"
    )
    result = subprocess.run(
        ["bash", str(shell), "-c", f"python -c {shlex.quote(probe)}"],
        cwd=pr,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
