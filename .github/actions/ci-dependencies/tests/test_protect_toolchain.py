"""Verify reviewer-writable paths are excluded before credentials are used."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ci-dependencies" / "reusable" / "protect_toolchain.sh"


@pytest.mark.parametrize("unsafe", ["", "directory", "executable", "owner"])
def test_protects_runner_files_and_rejects_writable_path(tmp_path, unsafe):
    cache = tmp_path / "cache"
    workspace = tmp_path / "workspace"
    runner_temp = tmp_path / "runner-temp"
    bins = tmp_path / "bin"
    for directory in (cache, workspace, runner_temp, bins):
        directory.mkdir()
    for directory in (cache, workspace, runner_temp):
        (directory / "file").write_text("fixture")
        (directory / "file").chmod(0o666)
        directory.chmod(0o777)
    sudo = bins / "sudo"
    sudo.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:3] == ['-n', '-u', 'reviewer']:\n"
        "    args = args[3:]\n"
        "    if args[0] == 'test': sys.exit(0 if args[-1] == os.environ.get('UNSAFE_PATH') else 1)\n"
        "    if args[0] == 'find':\n"
        "        if '-maxdepth' in args and os.environ['UNSAFE_KIND'] == 'executable': print('writable')\n"
        "        sys.exit(0)\n"
        "if args[0] == 'find':\n"
        "    if os.environ['UNSAFE_KIND'] == 'owner': print('owned')\n"
        "    sys.exit(0)\n"
        "os.execvp(args[0], args)\n"
    )
    sudo.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bins}:/usr/bin:/bin",
        "RUNNER_TOOL_CACHE": str(cache),
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_WORKSPACE": str(workspace),
        "UNSAFE_PATH": str(bins) if unsafe == "directory" else "",
        "UNSAFE_KIND": unsafe,
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    assert result.returncode == int(bool(unsafe)), result.stderr
    directories = (cache,) if unsafe == "owner" else (cache, workspace, runner_temp)
    for directory in directories:
        assert not (directory.stat().st_mode & 0o022)
        assert not ((directory / "file").stat().st_mode & 0o022)
    if unsafe:
        assert "reviewer" in result.stderr.lower()


def test_toolchain_is_protected_before_installing_dependencies():
    workflow = ROOT.parent / "workflows" / "reusable-bot-ai-review.yml"
    steps = yaml.safe_load(workflow.read_text())["jobs"]["review"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Install OpenCode") < names.index(
        "Install trusted CI dependencies"
    )
    assert names.index("Install trusted CI dependencies") < names.index(
        "Configure provider credentials"
    )
