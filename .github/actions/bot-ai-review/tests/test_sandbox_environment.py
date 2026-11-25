"""Check that review commands do not inherit the runner's configuration paths."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "reusable" / "sandbox_shell.sh"
PREPARE = SCRIPT.parent / "prepare_sandbox.sh"


def test_sandbox_uses_reviewer_configuration_and_drops_runner_environment(tmp_path):
    sudo = tmp_path / "sudo"
    sudo.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = sys.argv[sys.argv.index('/usr/bin/env'):]\n"
        "args = args[:args.index('/bin/bash')] + ['/usr/bin/env']\n"
        "os.execv(args[0], args)\n"
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
    }
    result = subprocess.run(
        [str(SCRIPT), "-c", "true"], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    environment = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert environment["HOME"] == "/home/reviewer"
    assert environment["XDG_CONFIG_HOME"] == "/home/reviewer/.config"
    assert environment["CHROME_BIN"] == "/opt/chrome/chrome"
    assert environment["SE_CHROMEDRIVER"] == "/opt/chrome/chromedriver"
    assert environment["GECKO_BIN"] == "/usr/bin/firefox"
    assert environment["SELENIUM_HEADLESS"] == "1"
    assert environment["CI_DEPS_CACHE"] == "/home/reviewer/.cache/ci-deps"
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
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "TEST_HOME": str(home),
    }
    result = subprocess.run(
        ["bash", str(PREPARE)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    venv = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True
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
