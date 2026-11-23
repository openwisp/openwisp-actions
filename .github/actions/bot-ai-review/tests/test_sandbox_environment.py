"""Check that review commands do not inherit the runner's configuration paths."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "reusable" / "sandbox_shell.sh"


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
    assert "NPM_CONFIG_USERCONFIG" not in environment
    assert "SECRET_SENTINEL" not in environment
