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
        with tempfile.TemporaryDirectory() as root:
            for directory in ("bin", "pr", "data", "shared-guidance"):
                os.mkdir(os.path.join(root, directory))
            for filename in ("pr.diff", "context.json", "history.json"):
                with open(os.path.join(root, "data", filename), "w") as f:
                    f.write("x")
            with open(os.path.join(root, "shared-guidance", "guidance.md"), "w") as f:
                f.write("")
            event = json.dumps(
                {
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
            )
            fake = os.path.join(root, "bin", "opencode")
            with open(fake, "w") as f:
                f.write(
                    "#!/bin/sh\n"
                    "if [ \"$1\" = debug ]; then echo '[]'; exit 0; fi\n"
                    'if [ "$1" = models ]; then exit 0; fi\n'
                    "printf '%s\\n' '" + event + "'\nexit 1\n"
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
            }
            result = subprocess.run([SCRIPT], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(root, "findings.json")))

    def test_final_review_receives_base_branch_guidance(self):
        with tempfile.TemporaryDirectory() as root:
            for directory in ("bin", "pr", "data", "shared-guidance"):
                os.mkdir(os.path.join(root, directory))
            for filename in ("pr.diff", "context.json", "history.json", "guidance.md"):
                with open(os.path.join(root, "data", filename), "w") as f:
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
                    'echo \'{"type":"text","part":{"text":"not JSON"}}\'\n'
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
            }
            subprocess.run([SCRIPT], env=env, check=True, capture_output=True)
            with open(os.path.join(root, "args")) as f:
                args = f.read().splitlines()
            self.assertIn(f"{root}/data/guidance.md", args)
