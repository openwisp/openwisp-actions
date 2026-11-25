"""Test that progress logging stays ordered and survives credential changes."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reusable",
    "print_progress.py",
)


def write(path, record):
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def start(command, timestamp=None):
    record = {"type": "tool_start", "args": ["-c", command]}
    if timestamp is not None:
        record["timestamp"] = timestamp
    return record


def completion(command, timestamp):
    state = {"status": "completed", "input": {"command": command}}
    part = {"tool": "bash", "state": state}
    return {"type": "tool_use", "timestamp": timestamp, "part": part}


class TestPrintProgress(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = directory.name
        self.auth = os.path.join(self.root, "auth.json")
        self.starts = os.path.join(self.root, "starts.jsonl")
        self.events = os.path.join(self.root, "events.jsonl")
        for path in (self.starts, self.events):
            open(path, "w").close()

    def follow(self, review, model="provider/model"):
        process = subprocess.Popen(
            [
                sys.executable,
                SCRIPT,
                self.auth,
                model,
                os.path.join(self.root, "missing-initial-auth.json"),
                os.path.join(self.root, "history"),
                str(review.pid),
                self.starts,
                self.events,
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.wait, timeout=10)
        self.addCleanup(process.kill)
        return process

    def review(self):
        # Stands in for the review: the printer exits when it ends, at the latest
        # after 30 seconds, so a missing line cannot block the test.
        review = subprocess.Popen(["sleep", "30"])
        self.addCleanup(review.wait)
        self.addCleanup(review.kill)
        return review

    def test_continues_after_an_incomplete_credential_file(self):
        with open(self.auth, "w") as f:
            f.write('{"github-copilot": {"access": "tok')
        review = self.review()
        process = self.follow(review, model="github-copilot/model")

        def check(command):
            write(self.events, start(command))
            return process.stdout.readline()

        self.assertEqual(
            check("echo secret-token"),
            "Tool call hidden: the credentials could not be read\n",
        )
        # Replace the file at once, so the printer cannot read it half written.
        with open(f"{self.auth}.new", "w") as f:
            json.dump({"github-copilot": {"access": "secret-token"}}, f)
        os.replace(f"{self.auth}.new", self.auth)
        self.assertEqual(check("./runtests"), "Started: ./runtests\n")
        self.assertEqual(
            check("echo secret-token"),
            "Tool call hidden: it contains a credential\n",
        )
        review.kill()
        review.wait()
        self.assertEqual(process.wait(timeout=10), 0)

    def test_records_read_in_one_pass_are_printed_in_order(self):
        write(self.starts, start("./first", 1))
        write(self.starts, start("./second", 3))
        write(self.events, completion("./first", 2))
        # All records are read in one pass, as when commands end quickly.
        review = subprocess.Popen(["true"])
        review.wait()
        process = self.follow(review)
        self.assertEqual(
            process.stdout.read().splitlines(),
            [
                "Started: ./first",
                "Tool: bash (completed) ./first",
                "Started: ./second",
            ],
        )

    def test_records_read_in_later_passes_are_printed_in_order(self):
        now = int(time.time() * 1000)
        write(self.starts, start("./first", now - 3000))
        # Later than now, so a slow test run cannot print it before the completion.
        write(self.starts, start("./second", now + 2000))
        process = self.follow(self.review())
        self.assertEqual(process.stdout.readline(), "Started: ./first\n")
        # The completion was read after the start of the next command.
        write(self.events, completion("./first", now - 2000))
        self.assertEqual(
            [process.stdout.readline(), process.stdout.readline()],
            ["Tool: bash (completed) ./first\n", "Started: ./second\n"],
        )
