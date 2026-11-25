"""Test that progress logging survives a credential file being rewritten."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reusable",
    "print_progress.py",
)


class TestPrintProgress(unittest.TestCase):
    def test_continues_after_an_incomplete_credential_file(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        auth = os.path.join(directory.name, "auth.json")
        with open(auth, "w") as f:
            f.write('{"github-copilot": {"access": "tok')
        process = subprocess.Popen(
            [sys.executable, SCRIPT, auth, "github-copilot/model"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(process.wait)
        self.addCleanup(process.stdout.close)

        def start(command):
            event = {"type": "tool_start", "args": ["-c", command]}
            process.stdin.write(json.dumps(event) + "\n")
            process.stdin.flush()
            return process.stdout.readline()

        self.assertEqual(
            start("echo secret-token"),
            "Tool call hidden: the credentials could not be read\n",
        )
        with open(auth, "w") as f:
            json.dump({"github-copilot": {"access": "secret-token"}}, f)
        self.assertEqual(start("./runtests"), "Started: ./runtests\n")
        self.assertEqual(
            start("echo secret-token"),
            "Tool call hidden: it contains a credential\n",
        )
        process.stdin.close()
        self.assertEqual(process.wait(timeout=10), 0)
