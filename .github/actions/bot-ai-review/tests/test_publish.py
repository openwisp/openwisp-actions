"""Test publication of AI reviews and dismissal of older reviews."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
SCRIPT = os.path.join(SCRIPTS, "publish.sh")
HEAD_SHA = "a" * 40
REVIEWS = [
    {
        "id": 1,
        "user": {"type": "Bot"},
        "body": "AI review of old provided by `p` / `m`",
        "state": "CHANGES_REQUESTED",
    },
    {
        "id": 2,
        "user": {"type": "Bot"},
        "body": "AI review of new provided by `p` / `m`",
        "state": "COMMENTED",
    },
]
FAKE_GH = """#!/usr/bin/env bash
echo "gh $*" >>"$STATE/log"
case "$*" in
  *"--jq .head.sha"*) echo "$REMOTE_HEAD" ;;
  "api --paginate "*) cat "$STATE/reviews.json" ;;
  "api -X POST "*) cat >"$STATE/review.json" ;;
esac
"""
FAKE_TOOL = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >>"$STATE/log"
if [ "$(basename "$0") $1" = "crit push" ] && [ "${FAIL_PUSH:-}" = 1 ]; then exit 1; fi
"""
FAILED = {
    "event": "comment",
    "verdict": "Review not completed",
    "summary": "- The model did not return a valid review.",
}
INCONCLUSIVE = {"event": "comment", "verdict": "Inconclusive", "summary": "- Unsure."}
LOOKS_GOOD = {"event": "comment", "verdict": "Looks good", "summary": "- Fine."}
APPROVED = {"event": "approve", "verdict": "Ready to merge", "summary": "- Fine."}
CHANGES = {"event": "request-changes", "verdict": "Needs changes", "summary": "- Bug."}
DECISION = {
    "event": "comment",
    "verdict": "Maintainer decision needed",
    "summary": "- Choose an approach.",
}


COMMENT = {"file": "a.py", "line": 1, "body": "x"}


def publish(
    findings, comments=(COMMENT,), remote_head=HEAD_SHA, fail_push=False, stage="review"
):
    with tempfile.TemporaryDirectory() as state:
        for name, content in (("gh", FAKE_GH), ("git", FAKE_TOOL), ("crit", FAKE_TOOL)):
            path = os.path.join(state, name)
            with open(path, "w") as f:
                f.write(content)
            os.chmod(path, 0o755)
        with open(os.path.join(state, "reviews.json"), "w") as f:
            reviews = [
                {
                    **review,
                    "body": review["body"].replace("AI review of ", f"AI {stage} of "),
                }
                for review in REVIEWS
            ]
            json.dump(reviews, f)
        path = os.path.join(state, "findings.json")
        with open(path, "w") as f:
            json.dump({**findings, "comments": list(comments)}, f)
        env = {
            "PATH": f"{state}:{os.environ['PATH']}",
            "STATE": state,
            "RUNNER_TEMP": state,
            "FINDINGS": path,
            "REPOSITORY": "openwisp/repo",
            "PR_NUMBER": "1",
            "HEAD_SHA": HEAD_SHA,
            "REMOTE_HEAD": remote_head,
            "FAIL_PUSH": str(int(fail_push)),
            "STAGE": stage,
            "MODEL": "provider/model",
        }
        result = subprocess.run([SCRIPT], env=env, capture_output=True)
        with open(os.path.join(state, "log")) as f:
            log = f.read().splitlines()
        review = os.path.join(state, "review.json")
        if os.path.exists(review):
            with open(review) as f:
                review = json.load(f)
        else:
            review = None
        if remote_head != HEAD_SHA or fail_push:
            return result.returncode, log
        assert result.returncode == 0, result.stderr
        return log, review


def dismissals(log):
    return [line for line in log if "dismissals" in line]


class TestPublish(unittest.TestCase):
    def test_changed_head_stops_publication_and_dismissal(self):
        status, log = publish(CHANGES, remote_head="b" * 40)
        self.assertNotEqual(status, 0)
        self.assertFalse(any(line.startswith("crit") for line in log))
        self.assertEqual(dismissals(log), [])

    def test_failed_publication_does_not_dismiss_reviews(self):
        status, log = publish(CHANGES, fail_push=True)
        self.assertNotEqual(status, 0)
        self.assertTrue(any(line.startswith("crit push") for line in log))
        self.assertEqual(dismissals(log), [])

    def test_keeps_change_requests_without_a_conclusion(self):
        for findings in (FAILED, INCONCLUSIVE, DECISION):
            with self.subTest(verdict=findings["verdict"]):
                log, _ = publish(findings)
                self.assertEqual(dismissals(log), [])

    def test_dismisses_change_requests_after_a_conclusion(self):
        for findings in (LOOKS_GOOD, APPROVED, CHANGES):
            with self.subTest(verdict=findings["verdict"]):
                log, _ = publish(findings)
                self.assertEqual(len(dismissals(log)), 1)
                self.assertIn("pulls/1/reviews/1/dismissals", dismissals(log)[0])

    def test_posts_line_comments_with_crit(self):
        log, review = publish(CHANGES)
        self.assertIsNone(review)
        self.assertTrue(any(line.startswith("crit push 1") for line in log))

    def test_posts_verdict_and_summary_without_line_comments(self):
        cases = [
            (APPROVED, "APPROVE"),
            (CHANGES, "REQUEST_CHANGES"),
            (FAILED, "COMMENT"),
        ]
        for findings, event in cases:
            with self.subTest(verdict=findings["verdict"]):
                log, review = publish(findings, comments=())
                self.assertFalse(any(line.startswith("crit") for line in log))
                self.assertEqual(review["event"], event)
                self.assertEqual(review["commit_id"], HEAD_SHA)
                self.assertNotIn("comments", review)
                self.assertIn(f"**Verdict: {findings['verdict']}**", review["body"])
                self.assertTrue(review["body"].endswith(findings["summary"]))

    def test_inconsistent_positive_reviews_keep_earlier_change_requests(self):
        for stage, verdict in (
            ("review", "Looks good"),
            ("security-review", "No issues found"),
        ):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                output = os.path.join(directory, "output.json")
                diff = os.path.join(directory, "pr.diff")
                with open(output, "w") as f:
                    json.dump(
                        {
                            "verdict": verdict,
                            "title": "T",
                            "summary": "S",
                            "security_perimeter": "NO",
                            "comments": [{**COMMENT, "severity": "P1", "title": "Bug"}],
                        },
                        f,
                    )
                with open(diff, "w") as f:
                    f.write("--- /dev/null\n+++ b/a.py\n@@ -0,0 +1 @@\n+x\n")
                result = subprocess.run(
                    [
                        sys.executable,
                        os.path.join(SCRIPTS, "lib", "extract_findings.py"),
                        output,
                        diff,
                        stage,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                findings = json.loads(result.stdout)
                self.assertEqual(findings["verdict"], "Review not completed")
                log, _ = publish(findings, comments=findings["comments"], stage=stage)
                self.assertEqual(dismissals(log), [])

    def test_unresolved_final_summary_keeps_earlier_change_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "output.json")
            diff = os.path.join(directory, "pr.diff")
            with open(output, "w") as f:
                json.dump(
                    {
                        "verdict": "Ready to merge",
                        "title": "T",
                        "summary": "##### Addressed\n- None\n\n"
                        "##### Outstanding\n- Bug\n\n##### Unclear\n- None",
                        "comments": [],
                    },
                    f,
                )
            with open(diff, "w") as f:
                f.write("--- /dev/null\n+++ b/a.py\n@@ -0,0 +1 @@\n+x\n")
            result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(SCRIPTS, "lib", "extract_findings.py"),
                    output,
                    diff,
                    "final-review",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            findings = json.loads(result.stdout)
            self.assertEqual(findings["verdict"], "Review not completed")
            log, _ = publish(
                findings, comments=findings["comments"], stage="final-review"
            )
            self.assertEqual(dismissals(log), [])


if __name__ == "__main__":
    unittest.main()
