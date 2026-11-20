"""Test synchronization of the review sandbox working copy."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
SCRIPT = os.path.join(SCRIPTS, "sync-copy.sh")


class TestSyncCopy(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.src = os.path.join(directory.name, "pr")
        self.dst = os.path.join(directory.name, "run")
        self.list = os.path.join(directory.name, "files")
        os.makedirs(os.path.join(self.src, "app"))
        self.write(self.src, "app/feature.py", "fixed")
        self.write(self.src, "app/old.py", "old")
        self.sync()

    def write(self, root, path, content):
        path = os.path.join(root, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def read(self, path):
        with open(os.path.join(self.dst, path)) as f:
            return f.read()

    def sync(self):
        subprocess.run(
            [SCRIPT, self.src, self.dst, self.list], check=True, capture_output=True
        )

    def test_removes_files_deleted_between_commands(self):
        os.remove(os.path.join(self.src, "app/feature.py"))
        self.sync()
        self.assertFalse(os.path.exists(os.path.join(self.dst, "app/feature.py")))

    def test_removes_the_old_name_of_a_renamed_file(self):
        os.rename(
            os.path.join(self.src, "app/old.py"), os.path.join(self.src, "app/new.py")
        )
        self.sync()
        self.assertFalse(os.path.exists(os.path.join(self.dst, "app/old.py")))
        self.assertEqual(self.read("app/new.py"), "old")

    def test_updates_changed_files(self):
        self.write(self.src, "app/feature.py", "reverted")
        self.sync()
        self.assertEqual(self.read("app/feature.py"), "reverted")

    def test_transfers_same_size_changes_with_same_timestamp(self):
        source = os.path.join(self.src, "app/feature.py")
        timestamp = os.stat(source).st_mtime_ns
        self.write(self.src, "app/feature.py", "other")
        os.utime(source, ns=(timestamp, timestamp))
        self.sync()
        self.assertEqual(self.read("app/feature.py"), "other")

    def test_replaces_directory_with_file_and_keeps_unrelated_cache(self):
        self.write(self.dst, "app/__pycache__/feature.pyc", "cache")
        self.write(self.dst, "other/cache", "keep")
        shutil.rmtree(os.path.join(self.src, "app"))
        self.write(self.src, "app", "replacement")
        self.sync()
        self.assertEqual(self.read("app"), "replacement")
        self.assertEqual(self.read("other/cache"), "keep")

    def test_retry_after_rsync_failure_preserves_manifest_and_cache(self):
        with open(self.list, "rb") as f:
            manifest = f.read()
        self.write(self.dst, "cache/data", "keep")
        os.remove(os.path.join(self.src, "app/old.py"))
        self.write(self.src, "app/new.py", "new")
        with tempfile.TemporaryDirectory() as binary:
            fake = os.path.join(binary, "rsync")
            with open(fake, "w") as f:
                f.write("#!/bin/sh\nexit 1\n")
            os.chmod(fake, 0o755)
            env = {**os.environ, "PATH": f"{binary}:{os.environ['PATH']}"}
            result = subprocess.run(
                [SCRIPT, self.src, self.dst, self.list], env=env, capture_output=True
            )
        self.assertNotEqual(result.returncode, 0)
        with open(self.list, "rb") as f:
            self.assertEqual(f.read(), manifest)
        self.sync()
        self.assertEqual(self.read("app/new.py"), "new")
        self.assertEqual(self.read("cache/data"), "keep")

    def test_keeps_files_created_by_commands(self):
        self.write(self.dst, "node_modules/lib/index.js", "dependency")
        self.write(self.dst, "app/__pycache__/feature.pyc", "cache")
        os.remove(os.path.join(self.src, "app/feature.py"))
        self.sync()
        self.assertEqual(self.read("node_modules/lib/index.js"), "dependency")
        self.assertEqual(self.read("app/__pycache__/feature.pyc"), "cache")

    def test_reuses_python_environment_after_source_update(self):
        venv = os.path.join(self.dst, ".venv")
        python = os.path.join(venv, "bin", "python")
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", venv],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                python,
                "-c",
                "import sysconfig; from pathlib import Path; "
                "Path(sysconfig.get_path('purelib'), 'test_dependency.py')"
                ".write_text('VALUE = 42')",
            ],
            check=True,
            capture_output=True,
        )
        self.write(self.src, "app/feature.py", "updated")
        self.sync()
        result = subprocess.run(
            [python, "-c", "import test_dependency; print(test_dependency.VALUE)"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), "42")
        self.assertEqual(self.read("app/feature.py"), "updated")

    def test_parallel_syncs_all_succeed(self):
        os.remove(os.path.join(self.src, "app/feature.py"))
        runs = [
            subprocess.Popen(
                [SCRIPT, self.src, self.dst, self.list],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(8)
        ]
        self.assertEqual([run.wait() for run in runs], [0] * 8)
        self.assertFalse(os.path.exists(os.path.join(self.dst, "app/feature.py")))


if __name__ == "__main__":
    unittest.main()
