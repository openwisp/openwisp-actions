"""Check the shared test entry point without running the full suite."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestRuntests(unittest.TestCase):
    def run_script(self, *arguments, status=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(ROOT / "runtests", root / "runtests")
            tests = root / ".github" / "actions" / "example" / "tests"
            tests.mkdir(parents=True)
            (tests / "test_example.py").touch()
            (root / "qa").mkdir()
            (root / "qa" / "test_lean_yaml.py").touch()
            (root / "qa" / "test_runtests.py").touch()
            python = root / "python"
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit "$STATUS"\n')
            python.chmod(0o755)
            return subprocess.run(
                [str(root / "runtests"), *arguments],
                cwd=root,
                env={
                    **os.environ,
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "STATUS": str(status),
                },
                capture_output=True,
                text=True,
            )

    def test_focused_file_is_forwarded(self):
        result = self.run_script(".github/actions/example/tests/test_example.py", "-v")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["-m", "pytest", ".github/actions/example/tests/test_example.py", "-v"],
        )

    def test_unsafe_options_are_rejected(self):
        result = self.run_script("--config=other")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unsupported", result.stderr.lower())
        self.assertEqual(result.stdout, "")

    def test_runner_failure_is_propagated(self):
        self.assertEqual(self.run_script(status=17).returncode, 17)
