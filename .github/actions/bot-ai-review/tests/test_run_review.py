"""Test review inputs and incomplete model runs."""

import json
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "run-review.sh",
)


class TestRunReview(unittest.TestCase):
    def test_failed_run_cannot_publish_partial_approval(self):
        event = {
            "type": "text",
            "part": {
                "text": json.dumps(
                    {
                        "verdict": "Ready to merge",
                        "title": "OK",
                        "summary": "Fine",
                        "comments": [],
                    }
                )
            },
        }
        root, result = self.run_review(event, status=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(root, "findings.json")))
        with open(os.path.join(root, "events.jsonl")) as f:
            self.assertEqual(json.load(f), event)
        self.assertIn(b"The model run did not complete (exit status: 1)", result.stdout)

    def test_final_review_receives_base_branch_guidance(self):
        event = {"type": "text", "part": {"text": "not JSON"}}
        root, result = self.run_review(event, guidance=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(root, "args")) as f:
            args = f.read().splitlines()
        self.assertIn(f"{root}/data/agents.md", args)

    def run_review(self, event, status=0, guidance=False):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = directory.name
        for name in ("bin", "pr", "data", "shared-guidance"):
            os.mkdir(os.path.join(root, name))
        files = ["pr.diff", "context.json", "history.json"]
        if guidance:
            files.append("agents.md")
        for name in files:
            with open(os.path.join(root, "data", name), "w") as f:
                f.write("guidance")
        with open(os.path.join(root, "shared-guidance", "guidance.md"), "w") as f:
            f.write("")
        fake = os.path.join(root, "bin", "opencode")
        with open(fake, "w") as f:
            f.write(
                "#!/bin/sh\n"
                "if [ \"$1\" = debug ]; then echo '[]'; exit 0; fi\n"
                'if [ "$1" = models ]; then exit 0; fi\n'
                'printf \'%s\\n\' "$@" >"$RUNNER_TEMP/args"\n'
                "printf '%s\\n' \"$EVENT\"\n"
                'exit "$MODEL_STATUS"\n'
            )
        os.chmod(fake, 0o755)
        env = {
            **os.environ,
            "PATH": f"{root}/bin:{os.environ['PATH']}",
            "RUNNER_TEMP": root,
            "PR_DIR": f"{root}/pr",
            "DATA_DIR": f"{root}/data",
            "MODEL": "provider/model",
            "STAGE": "final-review",
            "EVENT": json.dumps(event),
            "MODEL_STATUS": str(status),
        }
        return root, subprocess.run([SCRIPT], env=env, capture_output=True)
