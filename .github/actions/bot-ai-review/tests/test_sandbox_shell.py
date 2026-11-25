"""Test that the sandbox shell records each command before it runs."""

import json
import os
import subprocess
import tempfile
import time
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reusable",
    "sandbox_shell.sh",
)


class TestSandboxShell(unittest.TestCase):
    def run_shell(self, *args, starts=True):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = directory.name
        os.mkdir(os.path.join(root, "bin"))
        # Stand in for the sandbox user, which tests cannot switch to.
        sudo = os.path.join(root, "bin", "sudo")
        with open(sudo, "w") as f:
            f.write('#!/bin/sh\nprintf "%s\\n" "$@" >"$SUDO_ARGS"\n')
        os.chmod(sudo, 0o755)
        env = {
            **os.environ,
            "PATH": f"{root}/bin:{os.environ['PATH']}",
            "SUDO_ARGS": os.path.join(root, "sudo-args"),
        }
        log = os.path.join(root, "starts.jsonl")
        if starts:
            env["AI_REVIEW_STARTS"] = log
        result = subprocess.run(
            ["bash", SCRIPT, *args], env=env, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(env["SUDO_ARGS"]) as f:
            sudo_args = f.read().splitlines()
        return log, sudo_args

    def test_records_each_command_before_running_it(self):
        command = "echo \"$HOME\" && ./runtests -k 'x y'"
        before = time.time() * 1000
        log, sudo_args = self.run_shell("-c", command)
        with open(log) as f:
            (record,) = [json.loads(line) for line in f]
        self.assertTrue(before - 1 <= record.pop("timestamp") <= time.time() * 1000)
        self.assertEqual(record, {"type": "tool_start", "args": ["-c", command]})
        self.assertEqual(sudo_args[-2:], ["-c", command])

    def test_does_not_record_without_a_log(self):
        log, sudo_args = self.run_shell("-c", "true", starts=False)
        self.assertFalse(os.path.exists(log))
        self.assertEqual(sudo_args[-2:], ["-c", "true"])
