"""Test trusted request records used to coordinate CI and reviews."""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "reusable"))

from ci_requests import (  # noqa: E402
    AmbiguousCIError,
    GitHub,
    active_request,
    bounded_pages,
    check_ci,
    coordinate,
    could_have_triggered,
    finish,
    parse_record,
    record_body,
    register,
    resume,
    resume_record,
    wake,
    was_open_at,
)


class TestCIRequests(unittest.TestCase):
    def setUp(self):
        key = patch("ci_requests.STATE_KEY", b"test-only-key", create=True)
        key.start()
        self.addCleanup(key.stop)
        self.request = {
            "stage": "review",
            "head_sha": "a" * 40,
            "state": "waiting",
            "comment_id": 123,
            "record_id": 9,
            "repository": "openwisp/repo",
            "pr_number": 17,
        }
        self.comment = {
            "id": 9,
            "body": record_body(self.request, "Waiting for CI."),
            "performed_via_github_app": {"id": 42},
        }

    def test_rejects_forged_or_invalid_records(self):
        self.assertIsNone(parse_record(self.comment, 43))
        self.assertIsNone(
            parse_record({**self.comment, "performed_via_github_app": None}, 42)
        )
        self.assertIsNone(
            parse_record({**self.comment, "body": "<!-- ai-review-request { -->"}, 42)
        )

    def test_finds_only_active_matching_request(self):
        self.assertEqual(
            active_request([self.comment], 42, "review", "a" * 40), self.comment
        )
        self.assertIsNone(active_request([self.comment], 42, "final-review", "a" * 40))
        self.assertIsNone(active_request([self.comment], 42, "review", "b" * 40))
        done = {
            **self.comment,
            "body": record_body({**self.request, "state": "done"}, "Done."),
        }
        self.assertIsNone(active_request([done], 42, "review", "a" * 40))

    def test_record_round_trip(self):
        self.assertEqual(parse_record(self.comment, 42), self.request)
        self.assertNotIn("\n", json.dumps(self.request))

    def test_register_records_request_before_checking_ci(self):
        events = []

        class API:
            def comments(self, pr):
                events.append("comments")
                return []

            def create(self, pr, body):
                events.append("create")
                return 7

            def ci_run(self, pr):
                events.append("ci")
                return {
                    "id": 1,
                    "run_attempt": 1,
                    "status": "in_progress",
                    "html_url": "https://example/run",
                }

            def update(self, comment, body):
                events.append("update")

        result = register(API(), 42, 17, self.request, {"number": 17})
        self.assertEqual(result[0], "waiting")
        self.assertEqual(events, ["comments", "create", "update", "ci", "update"])

    def test_duplicate_does_not_start_another_request(self):
        class API:
            def comments(self, pr):
                return [self_comment]

            def ci_run(self, pr):
                return {
                    "id": 5,
                    "run_attempt": 1,
                    "status": "in_progress",
                    "html_url": "url",
                }

            def update(self, comment_id, body):
                self.body = body

        self_comment = self.comment
        self.assertEqual(register(API(), 42, 17, self.request, {})[0], "waiting")

    def test_stopped_runs_cannot_start_review(self):
        for run in (
            None,
            {
                "id": 1,
                "run_attempt": 1,
                "status": "completed",
                "conclusion": "cancelled",
                "html_url": "url",
            },
        ):
            with self.subTest(run=run):

                class API:
                    def comments(self, pr):
                        return []

                    def create(self, pr, body):
                        return 7

                    def ci_run(self, pr):
                        return run

                    def update(self, comment, body):
                        self.body = body

                api = API()
                self.assertEqual(register(api, 42, 17, self.request, {})[0], "stopped")
                self.assertIn('"state":"done"', api.body)

    def test_resumption_only_starts_a_waiting_request_once(self):
        class API:
            def ci_run(self, pr):
                return {
                    "id": 1,
                    "run_attempt": 1,
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "url",
                }

            def update(self, comment, body):
                self.body = body

        api = API()
        state, _, _ = resume(
            api, self.comment, 42, {"state": "open", "head": {"sha": "a" * 40}}
        )
        self.assertEqual(state, "ready")
        updated = {**self.comment, "body": api.body}
        self.assertEqual(
            resume(api, updated, 42, {"state": "open", "head": {"sha": "a" * 40}})[0],
            "ignored",
        )

    def test_changed_or_closed_pull_request_does_not_resume(self):
        class API:
            def update(self, comment, body):
                self.body = body

        for pr in (
            {"state": "closed", "head": {"sha": "a" * 40}},
            {"state": "open", "head": {"sha": "b" * 40}},
        ):
            with self.subTest(pr=pr):
                api = API()
                self.assertEqual(resume(api, self.comment, 42, pr)[0], "stopped")
                self.assertIn("review skipped", api.body)

    def test_api_failure_ends_request_and_notifies_maintainers(self):
        class API:
            def comments(self, pr):
                return []

            def create(self, pr, body):
                return 7

            def ci_run(self, pr):
                raise RuntimeError("API unavailable")

            def update(self, comment, body):
                self.body = body

        api = API()
        with self.assertRaisesRegex(RuntimeError, "API unavailable"):
            register(api, 42, 17, self.request, {})
        self.assertIn('"state":"done"', api.body)
        self.assertIn("Could not check CI", api.body)

    def test_resume_record_requires_dispatch_and_record_from_same_app_and_pr(self):
        dispatch = {
            "body": "/ai-review-resume 9",
            "performed_via_github_app": {"id": 42},
        }
        stored = {
            **self.comment,
            "issue_url": "https://api.github.com/repos/openwisp/repo/issues/17",
        }

        class API:
            def comment(self, comment_id):
                assert comment_id == 9
                return stored

        self.assertEqual(
            resume_record(API(), dispatch, 42, "openwisp/repo", 17), stored
        )
        self.assertIsNone(resume_record(API(), dispatch, 43, "openwisp/repo", 17))
        self.assertIsNone(resume_record(API(), dispatch, 42, "openwisp/repo", 18))
        forged = {**dispatch, "performed_via_github_app": None}
        self.assertIsNone(resume_record(API(), forged, 42, "openwisp/repo", 17))

    def test_resume_record_rejects_a_record_not_waiting_for_ci(self):
        dispatch = {
            "body": "/ai-review-resume 9",
            "performed_via_github_app": {"id": 42},
        }
        stored = {
            **self.comment,
            "body": record_body({**self.request, "state": "reviewing"}, "Reviewing."),
            "issue_url": "https://api.github.com/repos/openwisp/repo/issues/17",
        }

        class API:
            def comment(self, comment_id):
                return stored

        self.assertIsNone(resume_record(API(), dispatch, 42, "openwisp/repo", 17))

    def test_ready_request_returns_exact_run_and_original_review_parameters(self):
        request = {
            **self.request,
            "base_sha": "b" * 40,
            "model": "provider/model",
            "effort": "high",
        }
        pr = {"number": 17, "state": "open", "head": {"sha": "a" * 40}}

        class API:
            def pull(self, number):
                return pr

            def comments(self, number):
                return []

            def create(self, number, body):
                return 9

            def update(self, number, body):
                self.body = body

            def ci_run(self, pr):
                return {
                    "id": 12,
                    "run_attempt": 2,
                    "status": "completed",
                    "conclusion": "failure",
                    "html_url": "url",
                }

        result = coordinate(API(), 42, "openwisp/repo", 17, request, None)
        self.assertEqual(result["stage"], "review")
        self.assertEqual(result["run_id"], 12)
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(result["comment_id"], 123)

    def test_ci_completion_wakes_only_matching_app_waiters(self):
        run = {
            "path": ".github/workflows/ci.yml",
            "event": "pull_request",
            "head_sha": "a" * 40,
            "created_at": "2026-01-01T00:00:00Z",
        }

        class API:
            def wake_candidates(self, run):
                return [17]

            def wake_comments(self, number, created_at):
                return [
                    self_comment,
                    {**self_comment, "performed_via_github_app": None},
                ]

            def create(self, number, body):
                self.messages.append((number, body))

            messages = []

        self_comment = self.comment
        api = API()
        wake(api, 42, run)
        self.assertEqual(api.messages, [(17, "/ai-review-resume 9")])

    def test_other_workflow_completion_cannot_wake_requests(self):
        class API:
            def pulls_for_run(self, run):
                raise AssertionError("must not query unrelated workflow")

        wake(
            API(), 42, {"path": ".github/workflows/other.yml", "event": "pull_request"}
        )

    def test_fork_completion_discovers_pull_request_without_github_association(self):
        run = {
            "head_repository": {"full_name": "someone/repo"},
            "head_branch": "fix",
            "pull_requests": [],
        }
        prs = [
            [
                {"number": 17, "head": {"repo": {"full_name": "someone/repo"}}},
                {"number": 18, "head": {"repo": {"full_name": "someone/other"}}},
            ]
        ]
        with patch("ci_requests.gh", return_value=prs) as api:
            assert GitHub("openwisp/repo").pulls_for_run(run) == [{"number": 17}]
        self.assertIn("state=all", api.call_args.args[0])

    def test_ambiguous_fork_run_is_not_assigned_to_multiple_pull_requests(self):
        pr = {
            "number": 17,
            "state": "open",
            "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}},
        }
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [],
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh", return_value=[{"workflow_runs": [run]}]
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ), patch.object(
            api, "pull", side_effect=[pr, {**pr, "number": 18}]
        ):
            with self.assertRaisesRegex(ValueError, "multiple pull requests"):
                api.ci_run(pr)

    def test_finish_releases_active_request_and_explains_stale_pr(self):
        record = {
            **self.comment,
            "body": record_body({**self.request, "state": "reviewing"}, "Reviewing."),
        }

        class API:
            def comment(self, comment_id):
                return record

            def pull(self, pr_number):
                return {"state": "closed", "head": {"sha": "a" * 40}}

            def update(self, comment_id, body):
                self.body = body

        api = API()
        finish(api, 42, 17, 9, "failure")
        self.assertIn('"state":"done"', api.body)
        self.assertIn("changed or closed", api.body)

    def test_failed_review_workflow_does_not_leave_request_permanently_active(self):
        old = {**self.request, "state": "reviewing", "review_run_id": 321}
        comment = {**self.comment, "body": record_body(old, "Reviewing.")}

        class API:
            def comments(self, pr):
                return [comment]

            def workflow_run(self, run_id):
                return {"status": "completed"}

            def update(self, comment_id, body):
                self.updated = body

            def create(self, number, body):
                return 10

            def ci_run(self, pr):
                return None

        api = API()
        result = register(api, 42, 17, self.request, {})
        self.assertEqual(result[0], "stopped")
        self.assertIn('"state":"done"', api.updated)

    def test_resume_records_the_workflow_that_actually_starts_the_review(self):
        dispatch = {
            "body": "/ai-review-resume 9",
            "performed_via_github_app": {"id": 42},
        }
        stored = {
            **self.comment,
            "body": record_body({**self.request, "review_run_id": 111}, "Waiting."),
            "issue_url": "https://api.github.com/repos/openwisp/repo/issues/17",
        }

        class API:
            def comment(self, comment_id):
                return stored

            def pull(self, pr_number):
                return {"state": "open", "head": {"sha": "a" * 40}}

            def ci_run(self, pr):
                return {
                    "id": 1,
                    "run_attempt": 1,
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "url",
                }

            def update(self, comment_id, body):
                self.body = body

        api = API()
        result = coordinate(
            api, 42, "openwisp/repo", 17, {}, dispatch, review_run_id=777
        )
        self.assertIn('"review_run_id":777', api.body)
        self.assertEqual(result["review_run_id"], 777)

    def test_same_app_cannot_resume_a_tampered_record(self):
        tampered = {
            **self.comment,
            "body": self.comment["body"].replace(
                '"comment_id":123', '"comment_id":999'
            ),
        }
        self.assertIsNone(parse_record(tampered, 42))

    def test_signed_record_cannot_be_copied_to_a_different_comment(self):
        self.assertIsNone(parse_record({**self.comment, "id": 99}, 42))

    def test_missing_signing_key_fails_closed(self):
        with patch("ci_requests.STATE_KEY", b""):
            self.assertIsNone(parse_record(self.comment, 42))
            with self.assertRaisesRegex(ValueError, "signing key"):
                record_body(self.request, "Waiting.")

    def test_resuming_uses_saved_attempt_even_when_a_later_retry_is_running(self):
        saved = {**self.request, "run_id": 5, "attempt": 1}
        comment = {**self.comment, "body": record_body(saved, "Waiting.")}

        class API:
            def run_attempt(self, run_id, attempt):
                assert (run_id, attempt) == (5, 1)
                return {
                    "id": 5,
                    "run_attempt": 1,
                    "status": "completed",
                    "conclusion": "failure",
                    "html_url": "url",
                }

            def ci_run(self, pr):
                raise AssertionError(
                    "the later retry must not replace the saved attempt"
                )

            def update(self, comment_id, body):
                self.body = body

        api = API()
        state, _, run = resume(
            api, comment, 42, {"state": "open", "head": {"sha": "a" * 40}}
        )
        self.assertEqual(state, "ready")
        self.assertEqual(run["run_attempt"], 1)

    def test_repeated_command_recovers_waiting_request_without_creating_another(self):
        old = {
            **self.request,
            "run_id": 5,
            "attempt": 1,
            "base_sha": "b" * 40,
            "model": "p/m",
            "effort": "",
        }
        comment = {**self.comment, "body": record_body(old, "Waiting.")}
        pr = {"number": 17, "state": "open", "head": {"sha": "a" * 40}}

        class API:
            def pull(self, number):
                return pr

            def comments(self, number):
                return [comment]

            def run_attempt(self, run_id, attempt):
                return {
                    "id": 5,
                    "run_attempt": 1,
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "url",
                }

            def update(self, number, body):
                self.body = body

            def create(self, number, body):
                raise AssertionError("must reuse the existing request")

        request = {**old, "comment_id": 999}
        result = coordinate(API(), 42, "openwisp/repo", 17, request, None, 77)
        self.assertEqual(result["record_id"], 9)
        self.assertEqual(result["comment_id"], 123)
        self.assertEqual(result["run_id"], 5)

    def test_reads_saved_attempt_from_attempt_endpoint(self):
        with patch("ci_requests.gh", return_value=[{"id": 5, "run_attempt": 2}]) as gh:
            self.assertEqual(
                GitHub("openwisp/repo").run_attempt(5, 2)["run_attempt"], 2
            )
        gh.assert_called_once_with("repos/openwisp/repo/actions/runs/5/attempts/2")

    def test_associated_run_is_rejected_if_another_pr_shares_its_head(self):
        pr = {
            "number": 17,
            "state": "open",
            "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}},
        }
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [{"number": 17}],
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh", return_value=[{"workflow_runs": [run]}]
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ), patch.object(
            api, "pull", side_effect=[pr, {**pr, "number": 18}]
        ):
            with self.assertRaisesRegex(ValueError, "multiple pull requests"):
                api.ci_run(pr)

    def test_closed_pr_with_same_head_still_makes_ci_run_ambiguous(self):
        pr = {
            "number": 17,
            "state": "open",
            "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}},
        }
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [{"number": 17}],
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh", return_value=[{"workflow_runs": [run]}]
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ), patch.object(
            api, "pull", side_effect=[pr, {**pr, "number": 18, "state": "closed"}]
        ):
            with self.assertRaisesRegex(ValueError, "multiple pull requests"):
                api.ci_run(pr)

    def test_ambiguous_ci_run_is_explained_in_request_comment(self):
        class API:
            def comments(self, number):
                return []

            def create(self, number, body):
                return 7

            def ci_run(self, pr):
                raise AmbiguousCIError("multiple pull requests")

            def update(self, number, body):
                self.body = body

        api = API()
        with self.assertRaises(AmbiguousCIError):
            register(api, 42, 17, self.request, {})
        self.assertIn("multiple pull requests", api.body)

    def test_retargeted_pr_does_not_resume_old_waiting_request(self):
        old = {**self.request, "base_ref": "release"}
        comment = {**self.comment, "body": record_body(old, "Waiting.")}

        class API:
            def update(self, comment_id, body):
                self.body = body

            def ci_run(self, pr):
                raise AssertionError("A retargeted request must not check CI")

        api = API()
        pr = {"state": "open", "head": {"sha": "a" * 40}, "base": {"ref": "master"}}
        self.assertEqual(resume(api, comment, 42, pr)[0], "stopped")
        self.assertIn('"state":"done"', api.body)

    def test_new_request_after_retarget_does_not_reuse_old_base(self):
        old = {**self.request, "base_ref": "release"}
        comment = {**self.comment, "body": record_body(old, "Waiting.")}
        request = {**self.request, "base_ref": "master", "comment_id": 999}

        class API:
            def __init__(self):
                self.updates = []

            def comments(self, number):
                return [comment]

            def create(self, number, body):
                return 10

            def update(self, number, body):
                self.updates.append((number, body))

            def ci_run(self, pr):
                return None

        api = API()
        self.assertEqual(register(api, 42, 17, request, {})[0], "stopped")
        self.assertIn('"state":"done"', api.updates[0][1])
        self.assertEqual(api.updates[0][0], 9)
        self.assertEqual(api.updates[1][0], 10)

    def test_ci_created_before_retarget_is_not_used_for_new_base(self):
        pr = {"number": 17, "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}}}
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [{"number": 17}],
            "created_at": "2026-01-01T10:00:00Z",
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh",
            side_effect=[
                [{"workflow_runs": [run]}],
                [[{"event": "base_ref_changed", "created_at": "2026-01-01T11:00:00Z"}]],
            ],
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}]
        ), patch.object(
            api, "pull", return_value=pr
        ):
            with self.assertRaisesRegex(AmbiguousCIError, "base"):
                api.ci_run(pr)

    def test_ci_created_after_retarget_can_be_used(self):
        pr = {"number": 17, "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}}}
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [{"number": 17}],
            "created_at": "2026-01-01T11:00:00Z",
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh",
            side_effect=[
                [{"workflow_runs": [run]}],
                [[{"event": "base_ref_changed", "created_at": "2026-01-01T10:00:00Z"}]],
            ],
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}]
        ), patch.object(
            api, "pull", return_value=pr
        ):
            self.assertEqual(api.ci_run(pr), run)

    def test_ci_run_is_ambiguous_when_another_pr_on_the_branch_has_moved(self):
        pr = {"number": 17, "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}}}
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [{"number": 17}],
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh", return_value=[{"workflow_runs": [run]}]
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ):
            with self.assertRaisesRegex(AmbiguousCIError, "multiple pull requests"):
                api.ci_run(pr)

    def test_closed_pr_before_run_does_not_make_reused_branch_ambiguous(self):
        pr = {
            "number": 17,
            "created_at": "2026-09-02T09:20:31Z",
            "closed_at": None,
            "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}},
        }
        old = {
            "number": 18,
            "created_at": "2026-08-26T19:05:04Z",
            "closed_at": "2026-08-28T10:51:25Z",
        }
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [],
            "created_at": "2026-09-02T09:26:48Z",
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh", side_effect=[[{"workflow_runs": [run]}], [[]]]
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ), patch.object(
            api, "pull", side_effect=[pr, old]
        ):
            self.assertEqual(api.ci_run(pr), run)

    def test_other_pr_open_when_run_started_is_still_ambiguous_after_it_closes(self):
        pr = {
            "number": 17,
            "created_at": "2026-09-02T09:20:31Z",
            "closed_at": None,
            "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}},
        }
        old = {
            "number": 18,
            "created_at": "2026-08-26T19:05:04Z",
            "closed_at": "2026-09-03T10:51:25Z",
        }
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [],
            "created_at": "2026-09-02T09:26:48Z",
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh", return_value=[{"workflow_runs": [run]}]
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ), patch.object(
            api, "pull", side_effect=[pr, old]
        ), patch.object(
            api, "issue_events", return_value=[]
        ):
            with self.assertRaisesRegex(AmbiguousCIError, "multiple pull requests"):
                api.ci_run(pr)

    def test_uncertain_pr_dates_remain_candidates(self):
        self.assertTrue(could_have_triggered({}, "2026-09-02T09:26:48Z"))
        self.assertTrue(
            could_have_triggered({"created_at": "2026-09-02T09:26:48Z"}, None)
        )
        self.assertFalse(
            could_have_triggered(
                {"created_at": "2026-09-03T00:00:00Z"}, "2026-09-02T09:26:48Z"
            )
        )

    def test_waiting_request_resumes_once_and_allows_a_fresh_request_after_finishing(
        self,
    ):
        run = {
            "id": 5,
            "run_attempt": 1,
            "status": "in_progress",
            "html_url": "url",
            "path": ".github/workflows/ci.yml",
            "event": "pull_request",
            "head_sha": "a" * 40,
            "created_at": "2026-01-01T00:00:00Z",
        }
        pr = {"number": 17, "state": "open", "head": {"sha": "a" * 40}}

        class API:
            def __init__(self):
                self.items = []

            def pull(self, number):
                return pr

            def wake_candidates(self, completed):
                return [17]

            def wake_comments(self, number, created_at):
                return self.items[:]

            def comments(self, number):
                return self.items[:]

            def create(self, number, body):
                item = {
                    "id": len(self.items) + 1,
                    "body": body,
                    "performed_via_github_app": {"id": 42},
                    "issue_url": "https://api.github.com/repos/openwisp/repo/issues/17",
                }
                self.items.append(item)
                return item["id"]

            def comment(self, number):
                return self.items[number - 1].copy()

            def update(self, number, body):
                self.items[number - 1]["body"] = body

            def ci_run(self, current):
                return run

            def run_attempt(self, run_id, attempt):
                return run

        api = API()
        self.assertEqual(
            coordinate(api, 42, "openwisp/repo", 17, self.request.copy(), None, 1), {}
        )
        self.assertEqual(
            coordinate(api, 42, "openwisp/repo", 17, self.request.copy(), None, 2), {}
        )
        self.assertEqual(len(api.items), 1)
        run.update(status="completed", conclusion="success")
        wake(api, 42, run)
        dispatch = api.items[1]
        result = coordinate(api, 42, "openwisp/repo", 17, {}, dispatch, 3)
        self.assertEqual(result["run_id"], 5)
        self.assertEqual(coordinate(api, 42, "openwisp/repo", 17, {}, dispatch, 4), {})
        finish(api, 42, 17, result["record_id"], "success")
        self.assertEqual(
            coordinate(api, 42, "openwisp/repo", 17, self.request.copy(), None, 5)[
                "run_id"
            ],
            5,
        )

    def test_reopened_pr_is_excluded_when_it_was_closed_during_the_run(self):
        events = [
            {"event": "closed", "created_at": "2026-01-01T10:00:00Z"},
            {"event": "reopened", "created_at": "2026-01-01T12:00:00Z"},
        ]
        self.assertFalse(was_open_at(events, "2026-01-01T11:00:00Z"))
        self.assertTrue(was_open_at(events, "2026-01-01T13:00:00Z"))
        self.assertTrue(was_open_at(events, "2026-01-01T10:00:00Z"))

    def test_ci_lookup_uses_open_close_history_for_overlapping_candidates(self):
        pr = {
            "number": 17,
            "created_at": "2026-01-01T08:00:00Z",
            "closed_at": None,
            "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}},
        }
        other = {"number": 18, "created_at": "2026-01-01T08:00:00Z", "closed_at": None}
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [],
            "created_at": "2026-01-01T11:00:00Z",
        }
        events = [
            {"event": "closed", "created_at": "2026-01-01T10:00:00Z"},
            {"event": "reopened", "created_at": "2026-01-01T12:00:00Z"},
        ]
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh",
            side_effect=[[{"workflow_runs": [run]}], [[]], [events], [[]]],
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ), patch.object(
            api, "pull", side_effect=[pr, other]
        ):
            self.assertEqual(api.ci_run(pr), run)

    def test_historical_run_association_is_checked_against_pr_lifetimes(self):
        pr = {
            "number": 17,
            "created_at": "2026-09-02T09:20:31Z",
            "closed_at": None,
            "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}},
        }
        old = {
            "number": 18,
            "created_at": "2026-08-26T19:05:04Z",
            "closed_at": "2026-08-28T10:51:25Z",
        }
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [{"number": 17}, {"number": 18}],
            "created_at": "2026-09-02T09:26:48Z",
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh", side_effect=[[{"workflow_runs": [run]}], [[]]]
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ), patch.object(
            api, "pull", side_effect=[pr, old]
        ):
            self.assertEqual(api.ci_run(pr), run)

    def test_newest_run_with_overlapping_pr_associations_remains_ambiguous(self):
        pr = {
            "number": 17,
            "created_at": "2026-09-02T09:20:31Z",
            "closed_at": None,
            "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}},
        }
        other = {"number": 18, "created_at": "2026-08-26T19:05:04Z", "closed_at": None}
        run = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [{"number": 17}, {"number": 18}],
            "created_at": "2026-09-02T09:26:48Z",
        }
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh", side_effect=[[{"workflow_runs": [run]}], [[]], [[]]]
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ), patch.object(
            api, "pull", side_effect=[pr, other]
        ):
            with self.assertRaises(AmbiguousCIError):
                api.ci_run(pr)

    def test_newer_run_associated_with_another_pr_cannot_fall_back_to_old_run(self):
        pr = {"number": 17, "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}}}
        old = {
            "id": 1,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [{"number": 17}],
        }
        new = {**old, "id": 2, "pull_requests": [{"number": 18}]}
        api = GitHub("openwisp/repo")
        with patch(
            "ci_requests.gh", return_value=[{"workflow_runs": [old, new]}]
        ), patch.object(
            api, "pulls_for_run", return_value=[{"number": 17}, {"number": 18}]
        ), patch.object(
            api, "pull", side_effect=[pr, {**pr, "number": 18}]
        ):
            with self.assertRaises(AmbiguousCIError):
                api.ci_run(pr)

    def test_wake_candidates_exclude_prs_closed_before_the_run(self):
        run = {
            "created_at": "2026-01-02T00:00:00Z",
            "head_repository": {"full_name": "someone/repo"},
            "head_branch": "fix",
            "pull_requests": [],
        }
        old = {
            "number": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "closed_at": "2026-01-01T12:00:00Z",
            "head": {"repo": {"full_name": "someone/repo"}},
        }
        current = {**old, "number": 2, "closed_at": "2026-01-03T00:00:00Z"}
        with patch("ci_requests.gh_page", return_value=[old, current]):
            self.assertEqual(GitHub("openwisp/repo").wake_candidates(run), [2])

    def test_wake_comments_start_at_run_creation(self):
        with patch("ci_requests.gh_page", return_value=[]) as page:
            GitHub("openwisp/repo").wake_comments(17, "2026-01-02T00:00:00Z")
        self.assertIn("since=2026-01-02T00%3A00%3A00Z", page.call_args.args[0])

    def test_bounded_scan_reports_when_it_cannot_finish(self):
        with patch("ci_requests.gh_page", return_value=[{}] * 100) as page:
            with self.assertRaisesRegex(RuntimeError, "scan limit"):
                bounded_pages("example?per_page=100", 2)
        self.assertEqual(page.call_count, 2)

    def test_wake_reports_incomplete_comment_scan_and_checks_other_candidates(self):
        run = {
            "path": ".github/workflows/ci.yml",
            "event": "pull_request",
            "head_sha": "a" * 40,
            "created_at": "2026-01-01T00:00:00Z",
        }
        comment = self.comment

        class API:
            def __init__(self):
                self.messages = []

            def wake_candidates(self, run):
                return [16, 17]

            def wake_comments(self, number, created_at):
                if number == 16:
                    raise RuntimeError("CI completion scan limit reached")
                return [comment]

            def create(self, number, body):
                self.messages.append((number, body))

        api = API()
        wake(api, 42, run)
        self.assertIn("could not check", api.messages[0][1].lower())
        self.assertEqual(api.messages[0][0], 16)
        self.assertEqual(api.messages[1], (17, "/ai-review-resume 9"))

    def test_waiting_message_links_ci_and_names_the_commit(self):
        class API:
            def ci_run(self, pr):
                return {
                    "id": 5,
                    "run_attempt": 1,
                    "status": "in_progress",
                    "html_url": "https://example.test/ci",
                }

            def update(self, comment_id, body):
                self.body = body

        api = API()
        check_ci(api, 9, self.request.copy(), {})
        self.assertIn("Waiting for [CI to complete](https://example.test/ci)", api.body)
        self.assertIn("before reviewing aaaaaaa.", api.body)
        self.assertNotIn("`aaaaaaa`", api.body)

    def test_waiting_message_is_preserved_through_review_completion(self):
        run = {
            "id": 5,
            "run_attempt": 1,
            "status": "in_progress",
            "html_url": "https://example.test/ci",
        }
        request = self.request.copy()

        class API:
            def ci_run(self, pr):
                return run

            def run_attempt(self, run_id, attempt):
                return run

            def update(self, comment_id, body):
                self.body = body

            def comment(self, comment_id):
                return {**self_comment, "body": self.body}

            def pull(self, number):
                return {"state": "open", "head": {"sha": "a" * 40}}

        self_comment = self.comment
        api = API()
        check_ci(api, 9, request, {})
        waiting = api.body.split("\n\n<!--", 1)[0]
        run.update(status="completed", conclusion="success")
        check_ci(api, 9, request, {})
        self.assertTrue(api.body.startswith(waiting + "\n\nUpdate: review is running."))
        finish(api, 42, 17, 9, "success", "https://example.test/review")
        self.assertTrue(
            api.body.startswith(
                waiting + "\n\nUpdate: [review completed](https://example.test/review)."
            )
        )

    def test_missing_ci_explains_possible_causes(self):
        class API:
            def ci_run(self, pr):
                return None

            def update(self, comment_id, body):
                self.body = body

        api = API()
        self.assertEqual(check_ci(api, 9, self.request.copy(), {})[0], "stopped")
        self.assertIn("may not be visible yet", api.body)
        self.assertIn("branch or path filter", api.body)

    def test_published_review_link_is_kept_if_later_cleanup_fails(self):
        record = {
            **self.comment,
            "body": record_body({**self.request, "state": "reviewing"}, "Reviewing."),
        }

        class API:
            def comment(self, comment_id):
                return record

            def pull(self, pr_number):
                return {"state": "open", "head": {"sha": "a" * 40}}

            def update(self, comment_id, body):
                self.body = body

        api = API()
        finish(api, 42, 17, 9, "failure", "https://example.test/review")
        self.assertIn("[review completed](https://example.test/review)", api.body)

    def test_finished_review_reports_when_link_is_unavailable(self):
        record = {
            **self.comment,
            "body": record_body({**self.request, "state": "reviewing"}, "Reviewing."),
        }

        class API:
            def comment(self, comment_id):
                return record

            def pull(self, pr_number):
                return {"state": "open", "head": {"sha": "a" * 40}}

            def update(self, comment_id, body):
                self.body = body

        api = API()
        finish(api, 42, 17, 9, "success")
        self.assertIn("review completed, but the link is unavailable", api.body)
