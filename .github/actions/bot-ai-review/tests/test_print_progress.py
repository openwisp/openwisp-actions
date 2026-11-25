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
        events = os.path.join(directory.name, "events.jsonl")
        for path in (events, os.path.join(directory.name, "starts.jsonl")):
            open(path, "w").close()
        # Stands in for the review: the printer exits when it ends, at the latest
        # after 30 seconds, so a missing line cannot block the test.
        review = subprocess.Popen(["sleep", "30"])
        process = subprocess.Popen(
            [
                sys.executable,
                SCRIPT,
                auth,
                "github-copilot/model",
                os.path.join(directory.name, "missing-initial-auth.json"),
                os.path.join(directory.name, "history"),
                str(review.pid),
                os.path.join(directory.name, "starts.jsonl"),
                events,
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.wait, timeout=10)
        self.addCleanup(process.kill)
        self.addCleanup(review.wait)
        self.addCleanup(review.kill)

        def start(command):
            with open(events, "a") as f:
                f.write(json.dumps({"type": "tool_start", "args": ["-c", command]}))
                f.write("\n")
            return process.stdout.readline()

        self.assertEqual(
            start("echo secret-token"),
            "Tool call hidden: the credentials could not be read\n",
        )
        # Replace the file at once, so the printer cannot read it half written.
        with open(f"{auth}.new", "w") as f:
            json.dump({"github-copilot": {"access": "secret-token"}}, f)
        os.replace(f"{auth}.new", auth)
        self.assertEqual(start("./runtests"), "Started: ./runtests\n")
        self.assertEqual(
            start("echo secret-token"),
            "Tool call hidden: it contains a credential\n",
        )
        review.kill()
        review.wait()
        self.assertEqual(process.wait(timeout=10), 0)

    def test_records_read_in_one_pass_are_printed_in_order(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        starts = os.path.join(directory.name, "starts.jsonl")
        events = os.path.join(directory.name, "events.jsonl")
        with open(starts, "w") as f:
            for timestamp, command in ((1, "./first"), (3, "./second")):
                record = {"type": "tool_start", "timestamp": timestamp}
                record["args"] = ["-c", command]
                f.write(json.dumps(record) + "\n")
        with open(events, "w") as f:
            state = {"status": "completed", "input": {"command": "./first"}}
            event = {"type": "tool_use", "timestamp": 2}
            event["part"] = {"tool": "bash", "state": state}
            f.write(json.dumps(event) + "\n")
        # All records are read in one pass, as when commands end quickly.
        review = subprocess.Popen(["true"])
        review.wait()
        result = subprocess.run(
            [
                sys.executable,
                SCRIPT,
                os.path.join(directory.name, "auth.json"),
                "provider/model",
                os.path.join(directory.name, "initial-auth.json"),
                os.path.join(directory.name, "history"),
                str(review.pid),
                starts,
                events,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "Started: ./first",
                "Tool: bash (completed) ./first",
                "Started: ./second",
            ],
        )
