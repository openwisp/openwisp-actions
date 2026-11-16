import json
import os
import subprocess
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
FAKE_GH = f"""#!/usr/bin/env bash
echo "gh $*" >>"$STATE/log"
case "$*" in
  *"--jq .head.sha"*) echo {HEAD_SHA} ;;
  "api --paginate "*) cat "$STATE/reviews.json" ;;
  "api -X POST "*) cat >"$STATE/review.json" ;;
esac
"""
FAKE_TOOL = '#!/usr/bin/env bash\necho "$(basename "$0") $*" >>"$STATE/log"\n'
FAILED = {
    "event": "comment",
    "verdict": "Review not completed",
    "summary": "- The model did not return a valid review.",
}
INCONCLUSIVE = {"event": "comment", "verdict": "Inconclusive", "summary": "- Unsure."}
LOOKS_GOOD = {"event": "comment", "verdict": "Looks good", "summary": "- Fine."}
APPROVED = {"event": "approve", "verdict": "Ready to merge", "summary": "- Fine."}
CHANGES = {"event": "request-changes", "verdict": "Needs changes", "summary": "- Bug."}


COMMENT = {"file": "a.py", "line": 1, "body": "x"}


def publish(findings, comments=(COMMENT,)):
    with tempfile.TemporaryDirectory() as state:
        for name, content in (("gh", FAKE_GH), ("git", FAKE_TOOL), ("crit", FAKE_TOOL)):
            path = os.path.join(state, name)
            with open(path, "w") as f:
                f.write(content)
            os.chmod(path, 0o755)
        with open(os.path.join(state, "reviews.json"), "w") as f:
            json.dump(REVIEWS, f)
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
            "STAGE": "review",
            "MODEL": "provider/model",
        }
        subprocess.run([SCRIPT], env=env, check=True, capture_output=True)
        with open(os.path.join(state, "log")) as f:
            log = f.read().splitlines()
        review = os.path.join(state, "review.json")
        if os.path.exists(review):
            with open(review) as f:
                review = json.load(f)
        else:
            review = None
        return log, review


def dismissals(log):
    return [line for line in log if "dismissals" in line]


class TestPublish(unittest.TestCase):
    def test_keeps_change_requests_without_a_conclusion(self):
        for findings in (FAILED, INCONCLUSIVE):
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


if __name__ == "__main__":
    unittest.main()
