"""Test selection of CI runs for a particular pull request revision."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "reusable"))

from ci_results import (  # noqa: E402
    classify,
    gh,
    matching_runs,
    results,
    select_run,
    selected_results,
)


class TestCIRuns(unittest.TestCase):
    def setUp(self):
        self.pr = {
            "number": 17,
            "head": {"sha": "a" * 40, "ref": "fix", "repo": {"id": 2}},
        }
        self.run = {
            "id": 3,
            "event": "pull_request",
            "head_sha": "a" * 40,
            "head_branch": "fix",
            "head_repository": {"id": 2},
            "pull_requests": [],
            "status": "completed",
            "conclusion": "success",
        }

    def test_matches_fork_when_github_omits_pull_request_list(self):
        self.assertEqual(matching_runs([self.run], self.pr), [self.run])

    def test_does_not_match_another_fork_or_pull_request(self):
        other_fork = {**self.run, "head_repository": {"id": 4}}
        other_pr = {**self.run, "pull_requests": [{"number": 18}]}
        other_sha = {**self.run, "head_sha": "b" * 40}
        self.assertEqual(matching_runs([other_fork, other_pr, other_sha], self.pr), [])

    def test_ignores_non_pull_request_runs(self):
        self.assertEqual(matching_runs([{**self.run, "event": "push"}], self.pr), [])

    def test_classifies_only_success_and_failure_as_ready(self):
        self.assertEqual(classify({**self.run, "status": "in_progress"}), "waiting")
        for conclusion in ("success", "failure"):
            self.assertEqual(classify({**self.run, "conclusion": conclusion}), "ready")
        for conclusion in ("cancelled", "timed_out", "neutral", None):
            self.assertEqual(
                classify({**self.run, "conclusion": conclusion}), "stopped"
            )

    def test_results_use_selected_attempt_and_include_job_and_step_outcomes(self):
        run = {**self.run, "run_attempt": 2, "html_url": "https://example/run"}
        jobs = [
            {
                "jobs": [
                    {
                        "id": 9,
                        "name": "test",
                        "html_url": "https://example/job",
                        "conclusion": "failure",
                        "steps": [{"name": "test", "conclusion": "failure"}],
                    }
                ]
            }
        ]
        with patch("ci_results.gh", return_value=jobs) as gh:
            data = results("owner/repo", run)
        gh.assert_called_once_with(
            "repos/owner/repo/actions/runs/3/attempts/2/jobs?per_page=100"
        )
        self.assertEqual(data["attempt"], 2)
        self.assertEqual(data["jobs"][0]["steps"][0]["conclusion"], "failure")
        self.assertEqual(data["jobs"][0]["html_url"], "https://example/job")

    def test_failed_run_includes_failed_job_excerpts(self):
        run = {
            **self.run,
            "run_attempt": 2,
            "html_url": "https://example/run",
            "conclusion": "failure",
        }
        with patch("ci_results.gh", return_value=[{"jobs": []}]), patch(
            "ci_results.failed_logs", return_value="excerpt"
        ) as logs:
            data = results("owner/repo", run)
        logs.assert_called_once_with("owner/repo", 3, 2)
        self.assertEqual(data["failed_job_excerpts"], "excerpt")

    def test_matches_run_for_exact_pr_when_github_supplies_associations(self):
        associated = {**self.run, "pull_requests": [{"number": 17}]}
        self.assertEqual(matching_runs([associated], self.pr), [associated])

    def test_selects_newest_matching_run_and_reports_missing(self):
        earlier = {**self.run, "id": 2, "status": "in_progress"}
        later = {**self.run, "id": 4}
        self.assertEqual(select_run([earlier, later], self.pr), later)
        self.assertIsNone(select_run([], self.pr))

    def test_selected_attempt_must_match_expected_commit(self):
        run = {**self.run, "run_attempt": 2, "html_url": "url"}
        with patch("ci_results.gh", return_value=[run]):
            with self.assertRaisesRegex(ValueError, "commit"):
                selected_results("owner/repo", 3, 2, "b" * 40)

    def test_selected_attempt_supplies_evidence_even_if_run_is_later_retried(self):
        run = {**self.run, "run_attempt": 2, "html_url": "url"}
        with patch("ci_results.gh", side_effect=[[run], [{"jobs": []}]]) as api:
            data = selected_results("owner/repo", 3, 2, "a" * 40)
        self.assertEqual(data["attempt"], 2)
        self.assertEqual(
            api.call_args_list[0].args[0], "repos/owner/repo/actions/runs/3/attempts/2"
        )

    def test_github_pagination_parses_each_json_response(self):
        with patch(
            "ci_results.subprocess.check_output",
            return_value='{"jobs": [1]}\n{"jobs": [2]}\n',
        ):
            self.assertEqual(gh("example"), [{"jobs": [1]}, {"jobs": [2]}])
