"""Verify reviewer-writable paths are excluded before credentials are used."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ci-dependencies" / "reusable" / "protect_toolchain.sh"


@pytest.mark.parametrize(
    "unsafe",
    [
        "",
        "directory",
        "executable",
        "owner",
        "protected",
        "runtime",
        "unreadable",
        "inaccessible",
    ],
)
def test_protects_runner_files_and_rejects_writable_path(tmp_path, unsafe):
    cache = tmp_path / "cache"
    workspace = tmp_path / "workspace"
    runner_temp = tmp_path / "runner-temp"
    home = tmp_path / "home"
    bins = tmp_path / "bin"
    for directory in (cache, workspace, runner_temp, home, bins):
        directory.mkdir()
    runtime_bin = cache / "runtime" / "bin"
    runtime_bin.mkdir(parents=True)
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
        "    if args[:2] == ['test', '-x']: "
        "sys.exit(1 if args[-1] == os.environ.get('UNSAFE_PATH') "
        "and os.environ['UNSAFE_KIND'] == 'inaccessible' else 0)\n"
        "    if args[:2] == ['test', '-r']: "
        "sys.exit(1 if args[-1] == os.environ.get('UNSAFE_PATH') "
        "and os.environ['UNSAFE_KIND'] == 'unreadable' else 0)\n"
        "    if args[0] == 'test':\n"
        "        unsafe = args[-1] == os.environ.get('UNSAFE_PATH') "
        "and os.environ['UNSAFE_KIND'] == 'directory'\n"
        "        sys.exit(0 if unsafe else 1)\n"
        "    if args[0] == 'find':\n"
        "        if '-maxdepth' in args and args[2] == os.environ.get('UNSAFE_PATH') "
        "and os.environ['UNSAFE_KIND'] == 'executable': print('writable')\n"
        "        if '-maxdepth' not in args and os.environ['UNSAFE_KIND'] == 'protected': print('writable')\n"
        "        if '-L' in args and '-maxdepth' not in args "
        "and os.environ['UNSAFE_KIND'] == 'runtime': print('writable')\n"
        "        sys.exit(0)\n"
        "if args[0] == 'find':\n"
        "    if os.environ['UNSAFE_KIND'] == 'owner': print('owned')\n"
        "    sys.exit(0)\n"
        "os.execvp(args[0], args)\n"
    )
    sudo.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bins}:{runtime_bin}:/usr/bin:/bin",
        "RUNNER_TOOL_CACHE": str(cache),
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_WORKSPACE": str(workspace),
        "HOME": str(home),
        "UNSAFE_PATH": (
            str(bins)
            if unsafe in ("directory", "executable", "unreadable", "inaccessible")
            else ""
        ),
        "UNSAFE_KIND": unsafe,
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    assert result.returncode == int(
        unsafe in ("owner", "protected", "runtime")
    ), result.stderr
    directories = (
        (cache,)
        if unsafe in ("owner", "protected")
        else (cache, workspace, runner_temp)
    )
    for directory in directories:
        assert not (directory.stat().st_mode & 0o022)
        assert not ((directory / "file").stat().st_mode & 0o022)
    if unsafe in ("owner", "protected", "runtime"):
        assert "reviewer" in result.stderr.lower()
    if unsafe in ("directory", "executable", "unreadable"):
        assert str(bins) not in result.stdout.strip().split(":")
        assert "/usr/bin" in result.stdout.strip().split(":")
    if unsafe == "inaccessible":
        assert str(bins) in result.stdout.strip().split(":")


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
    steps_by_name = {step.get("name"): step for step in steps}
    for name in (
        "Configure provider credentials",
        "Fetch pull request discussion",
        "Run review",
    ):
        assert "safe_path" in steps_by_name[name]["env"]["PATH"]
