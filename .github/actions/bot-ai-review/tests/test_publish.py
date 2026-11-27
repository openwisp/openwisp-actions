"""Test publication of AI reviews and dismissal of older reviews."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reusable"
)
SCRIPT = os.path.join(SCRIPTS, "publish.sh")
HEAD_SHA = "a" * 40
REVIEWS = [
    {
        "id": 1,
        "user": {"type": "Bot", "login": "openwisp-companion[bot]"},
        "body": "AI review of old provided by `p` / `m`",
        "state": "CHANGES_REQUESTED",
    },
    {
        "id": 2,
        "user": {"type": "Bot", "login": "openwisp-companion[bot]"},
        "body": "AI review of new provided by `p` / `m`",
        "state": "COMMENTED",
    },
    {
        "id": 0,
        "user": {"type": "Bot", "login": "another[bot]"},
        "body": "AI review of old provided by `p` / `m`",
        "state": "CHANGES_REQUESTED",
    },
]
FAKE_GH = """#!/usr/bin/env bash
echo "gh $*" >>"$STATE/log"
case "$*" in
  *"--jq .head.sha"*) echo "$REMOTE_HEAD" ;;
  *"--jq .state"*) echo "${REMOTE_STATE:-open}" ;;
  *"--jq .base.ref"*) echo "${REMOTE_BASE:-master}" ;;
  *"issues/comments/9 --jq .user.id"*) echo 42 ;;
  *"/dismissals"*) if [ "${FAIL_DISMISS:-}" = 1 ]; then echo 'dismissal denied' >&2; exit 1; fi ;;
  "api --paginate "*) if [ "${FAIL_LIST:-}" = 1 ]; then exit 1; fi; cat "$STATE/reviews.json" ;;
  "api -X POST "*)
    cat >"$STATE/request.json"
    if [ "${FAIL_POST:-}" = 1 ]; then echo 'network failure' >&2; exit 1; fi
    if [ "${FAIL_FOLLOWUP:-}" = 1 ] && [ -f "$STATE/review.json" ]; then
      echo 'continuation failed' >&2; exit 1
    fi
    if jq -e '(.body | length) > 65536' "$STATE/request.json" >/dev/null; then
      echo 'gh: body is too long (HTTP 422)' >&2; exit 1
    fi
    if [ "${FAIL_LARGE:-}" = 1 ] && jq -e '.comments | length > 0' "$STATE/request.json" >/dev/null; then
      printf 'HTTP/2.0 422 Unprocessable Entity\r\nContent-Type: application/json\r\n\r\n'
      echo '{"message":"Validation Failed","errors":[{"message":"Diff entry a.py diff is too large"}]}'
      echo 'gh: Validation Failed (HTTP 422)' >&2; exit 1
    fi
    if [ -f "$STATE/review.json" ]; then
      jq -c . "$STATE/request.json" >>"$STATE/notices.jsonl"
    else
      cp "$STATE/request.json" "$STATE/review.json"
    fi
    if [[ "$*" == *--include* ]]; then
      printf 'HTTP/2.0 200 OK\r\nContent-Type: application/json\r\n\r\n%s' "$REVIEW_RESPONSE"
    fi
    jq -r '"posted " + .event' "$STATE/request.json" >>"$STATE/log" ;;
esac
"""
FAKE_TOOL = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >>"$STATE/log"
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
    findings,
    comments=(COMMENT,),
    remote_head=HEAD_SHA,
    fail_push=False,
    stage="review",
    remote_state="open",
    ci_aware=False,
    ci_standard_status="unknown",
    ci_standard_missing="",
    remote_base="master",
    capture_output=False,
    lookup_user_id=42,
    fail_dismiss=False,
    fail_list=False,
    fail_large=False,
    fail_followup=False,
    extra_reviews=(),
    missing_review_id=False,
):
    with tempfile.TemporaryDirectory() as state:
        for name, content in (("gh", FAKE_GH), ("git", FAKE_TOOL)):
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
            if findings["event"] == "request-changes":
                reviews[1]["state"] = "CHANGES_REQUESTED"
            reviews.extend(extra_reviews)
            if ci_aware:
                reviews.append(
                    {
                        "id": 3,
                        "user": {"type": "Bot", "id": lookup_user_id},
                        "body": "AI review <!-- ai-review-run 123-1 -->",
                        "html_url": "https://example.test/review/3",
                        "state": "COMMENTED",
                    }
                )
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
            "REMOTE_STATE": remote_state,
            "BASE_REF": "master",
            "REMOTE_BASE": remote_base,
            "CI_AWARE": str(ci_aware).lower(),
            "CI_STANDARD_STATUS": ci_standard_status,
            "CI_STANDARD_MISSING": ci_standard_missing,
            "FAIL_PUSH": str(int(fail_push)),
            "FAIL_DISMISS": str(int(fail_dismiss)),
            "FAIL_LIST": str(int(fail_list)),
            "FAIL_POST": str(int(fail_push)),
            "FAIL_LARGE": str(int(fail_large)),
            "FAIL_FOLLOWUP": str(int(fail_followup)),
            "REVIEW_RESPONSE": "{}" if missing_review_id else '{"id":2}',
            "STAGE": stage,
            "MODEL": "provider/model",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_OUTPUT": os.path.join(state, "github_output"),
            "RECORD_ID": "9",
        }
        result = subprocess.run(["bash", SCRIPT], env=env, capture_output=True)
        if fail_dismiss:
            assert (
                b"Published the review, but could not dismiss earlier review 1"
                in result.stdout
            )
        if fail_list:
            assert (
                b"Published the review, but could not list earlier reviews"
                in result.stdout
            )
        with open(os.path.join(state, "log")) as f:
            log = f.read().splitlines()
        review = os.path.join(state, "review.json")
        if os.path.exists(review):
            with open(review) as f:
                review = json.load(f)
        else:
            review = None
        notice_path = os.path.join(state, "notices.jsonl")
        if os.path.exists(notice_path):
            with open(notice_path) as f:
                for line in f:
                    log.append("notice " + json.loads(line)["body"])
        if (
            remote_head != HEAD_SHA
            or fail_push
            or fail_followup
            or remote_state != "open"
            or remote_base != "master"
        ):
            return result.returncode, log
        assert result.returncode == 0, result.stderr
        if capture_output:
            output = os.path.join(state, "github_output")
            if os.path.exists(output):
                with open(output) as output_file:
                    return log, review, output_file.read()
            return log, review, ""
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
        self.assertTrue(any("api -X POST" in line for line in log))
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

    def test_posts_line_comments_with_review(self):
        log, review = publish(CHANGES)
        self.assertEqual(
            review["comments"],
            [{"path": "a.py", "line": 1, "side": "RIGHT", "body": "x"}],
        )

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
                        os.path.join(SCRIPTS, "extract_findings.py"),
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
                    os.path.join(SCRIPTS, "extract_findings.py"),
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

    def test_review_discloses_when_ci_was_not_awaited(self):
        _, review = publish(APPROVED, comments=(), stage="final-review")
        self.assertEqual(review["event"], "APPROVE")
        self.assertIn("CI was not checked or awaited", review["body"])
        self.assertIn(
            "https://github.com/openwisp/openwisp-actions/issues/39", review["body"]
        )

    def test_closed_pull_request_stops_publication(self):
        status, log = publish(APPROVED, comments=(), remote_state="closed")
        self.assertNotEqual(status, 0)
        self.assertFalse(any("api -X POST" in line for line in log))

    def test_ci_aware_review_omits_fallback_notice(self):
        _, review = publish(APPROVED, comments=(), ci_aware=True)
        self.assertNotIn("CI was not checked or awaited", review["body"])

    def test_review_reports_missing_ci_entry_points_without_changing_verdict(self):
        _, review = publish(
            APPROVED,
            comments=(),
            ci_standard_status="missing",
            ci_standard_missing=".github/workflows/ci.yml, install-ci-deps.sh",
        )
        self.assertEqual(review["event"], "APPROVE")
        self.assertIn(".github/workflows/ci.yml, install-ci-deps.sh", review["body"])

    def test_review_distinguishes_unknown_check_from_missing_files(self):
        _, review = publish(APPROVED, comments=(), ci_standard_status="unknown")
        self.assertIn("could not be checked", review["body"])

    def test_review_does_not_claim_present_files_are_missing(self):
        _, review = publish(APPROVED, comments=(), ci_standard_status="present")
        self.assertNotIn("Missing CI entry points", review["body"])
        self.assertNotIn("could not be checked", review["body"])

    def test_retargeted_pull_request_stops_publication(self):
        status, log = publish(APPROVED, comments=(), remote_base="release")
        self.assertNotEqual(status, 0)
        self.assertFalse(any("api -X POST" in line for line in log))

    def test_ci_aware_publication_returns_exact_review_link(self):
        for comments in ((), (COMMENT,)):
            with self.subTest(comments=comments):
                _, _, output = publish(
                    APPROVED, comments=comments, ci_aware=True, capture_output=True
                )
                self.assertEqual(output, "review_url=https://example.test/review/3\n")

    def test_review_link_does_not_match_another_bot(self):
        _, _, output = publish(
            APPROVED, comments=(), ci_aware=True, capture_output=True, lookup_user_id=43
        )
        self.assertEqual(output, "")

    def test_dismissal_failure_does_not_report_publication_failure(self):
        log, review = publish(APPROVED, comments=(), fail_dismiss=True)
        self.assertEqual(review["event"], "APPROVE")
        self.assertEqual(len(dismissals(log)), 1)
        self.assertTrue(
            any(line.startswith("notice ") and "review 1" in line for line in log)
        )

    def test_review_listing_failure_does_not_report_publication_failure(self):
        log, review = publish(APPROVED, comments=(), fail_list=True)
        self.assertEqual(review["event"], "APPROVE")
        self.assertEqual(dismissals(log), [])
        self.assertTrue(
            any(line.startswith("notice ") and "earlier" in line for line in log)
        )

    def test_publication_uses_prefetched_commit(self):
        log, _ = publish(APPROVED, comments=())
        self.assertTrue(any(line.startswith("git checkout ") for line in log))
        self.assertFalse(any(line.startswith("git fetch ") for line in log))

    def test_large_diff_rejection_preserves_every_finding_in_review(self):
        comments = (COMMENT, {"file": "b.py", "line": 9, "body": "details"})
        log, review = publish(CHANGES, comments=comments, fail_large=True)
        self.assertNotIn("comments", review)
        self.assertEqual(review["event"], "REQUEST_CHANGES")
        self.assertIn("a.py:1", review["body"])
        self.assertIn("b.py:9", review["body"])
        self.assertIn("details", review["body"])
        self.assertEqual(len(dismissals(log)), 1)

    def test_large_diff_fallback_splits_long_findings(self):
        comments = (
            {"file": "a.py", "line": 1, "body": "λ" * 33000},
            {"file": "b.py", "line": 9, "body": "Ω" * 33000},
        )
        log, review = publish(CHANGES, comments=comments, fail_large=True)
        notices = "".join(line[7:] for line in log if line.startswith("notice "))
        combined = review["body"] + notices
        self.assertIn("a.py:1", combined)
        self.assertIn("b.py:9", combined)
        self.assertEqual(combined.count("λ"), 33000)
        self.assertEqual(combined.count("Ω"), 33000)

    def test_split_fallback_keeps_ci_marker_in_first_review(self):
        findings = {**CHANGES, "summary": "λ" * 33000}
        log, review, output = publish(
            findings, fail_large=True, ci_aware=True, capture_output=True
        )
        marker = "<!-- ai-review-run 123-1 -->"
        self.assertIn(marker, review["body"])
        self.assertFalse(
            any(marker in line for line in log if line.startswith("notice "))
        )
        self.assertEqual(output, "review_url=https://example.test/review/3\n")

    def test_split_fallback_posts_approval_after_findings(self):
        comments = (COMMENT, {"file": "b.py", "line": 9, "body": "λ" * 33000})
        log, review = publish(APPROVED, comments=comments, fail_large=True)
        self.assertEqual(review["event"], "COMMENT")
        posts = [line for line in log if "api -X POST" in line]
        self.assertGreaterEqual(len(posts), 4)
        self.assertEqual(
            [line for line in log if line.startswith("posted ")][-1], "posted APPROVE"
        )

    def test_failed_continuation_does_not_approve(self):
        comments = (COMMENT, {"file": "b.py", "line": 9, "body": "λ" * 33000})
        status, log = publish(
            APPROVED, comments=comments, fail_large=True, fail_followup=True
        )
        self.assertNotEqual(status, 0)
        self.assertNotIn("posted APPROVE", log)
        self.assertEqual(dismissals(log), [])

    def test_split_approval_marks_the_final_review(self):
        comments = (COMMENT, {"file": "b.py", "line": 9, "body": "λ" * 33000})
        log, review, output = publish(
            APPROVED,
            comments=comments,
            fail_large=True,
            ci_aware=True,
            capture_output=True,
        )
        marker = "<!-- ai-review-run 123-1 -->"
        self.assertNotIn(marker, review["body"])
        self.assertIn(marker, [line for line in log if line.startswith("notice ")][-1])
        self.assertEqual(output, "review_url=https://example.test/review/3\n")

    def test_continuation_cannot_supersede_the_current_change_request(self):
        continuation = {
            "id": 3,
            "user": {"login": "openwisp-companion[bot]"},
            "body": "AI review of quoted text",
            "state": "COMMENTED",
        }
        log, _ = publish(CHANGES, extra_reviews=(continuation,))
        self.assertEqual(len(dismissals(log)), 1)
        self.assertIn("pulls/1/reviews/1/dismissals", dismissals(log)[0])

    def test_missing_review_id_keeps_earlier_change_requests(self):
        log, _ = publish(CHANGES, missing_review_id=True)
        self.assertEqual(dismissals(log), [])
        self.assertTrue(
            any(line.startswith("notice ") and "earlier" in line for line in log)
        )


if __name__ == "__main__":
    unittest.main()
