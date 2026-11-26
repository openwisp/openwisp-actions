"""Check filesystem write restrictions with the real Linux kernel."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "reusable/write_sandbox.py"


def test_child_process_can_only_write_in_the_review_directory(tmp_path):
    writable = tmp_path / "review"
    writable.mkdir()
    protected = tmp_path / "runner-file"
    protected.write_text("unchanged")
    (writable / "link").symlink_to(protected)
    probe = """
from pathlib import Path
import sys

root, outside = map(Path, sys.argv[1:])
assert outside.read_text() == 'unchanged'
(root / 'result').write_text('test output')
for path in (outside, root / 'link', outside.parent / 'new-file'):
    try:
        path.write_text('test write')
    except PermissionError:
        pass
    else:
        raise AssertionError(f'Write was not restricted: {path}')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPT),
            str(writable),
            "--",
            sys.executable,
            "-I",
            "-c",
            probe,
            str(writable),
            str(protected),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert (writable / "result").read_text() == "test output"
    assert protected.read_text() == "unchanged"


def test_does_not_launch_command_if_rule_cannot_be_installed(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPT),
            str(tmp_path / "missing"),
            "--",
            sys.executable,
            "-I",
            "-c",
            "print('unexpected launch')",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "Could not restrict reviewer writes" in result.stderr
    assert not result.stdout
