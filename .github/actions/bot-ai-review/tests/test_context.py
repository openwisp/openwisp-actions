"""Test the pull request context supplied to reviews."""

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reusable"
)
sys.path.insert(0, SCRIPTS)

from context import MAX_ISSUES, main, references  # noqa: E402

REPOSITORY = "openwisp/openwisp-controller"


class TestReferences(unittest.TestCase):
    def test_finds_issue_references(self):
        body = (
            "Closes #15.\n"
            "Related to openwisp/openwisp-utils#824 and\n"
            "https://github.com/openwisp/openwisp-users/issues/7"
        )
        self.assertEqual(
            references(body, REPOSITORY, 1),
            [
                (REPOSITORY, 15),
                ("openwisp/openwisp-utils", 824),
                ("openwisp/openwisp-users", 7),
            ],
        )

    def test_ignores_other_owners_and_the_pull_request_itself(self):
        body = (
            "other/repo#3 https://github.com/other/repo/issues/4 "
            "notopenwisp/repo#5 https://github.com/openwisp/x/pull/6 "
            "## Heading #1"
        )
        self.assertEqual(references(body, REPOSITORY, 1), [])

    def test_removes_duplicates_and_limits_references(self):
        body = " ".join(f"#{n} #{n}" for n in range(2, 20))
        self.assertEqual(
            references(body, REPOSITORY, 1),
            [(REPOSITORY, n) for n in range(2, 2 + MAX_ISSUES)],
        )


class TestMain(unittest.TestCase):
    def test_issue_lookup_failure_is_visible_to_reviewer(self):
        api = f"repos/{REPOSITORY}"
        error = subprocess.CalledProcessError(1, "gh", stderr="HTTP 503")
        with redirect_stderr(io.StringIO()) as stderr:
            result = self.run_main(
                {
                    f"{api}/pulls/1": {"title": "Fix", "body": "#2"},
                    f"{api}/issues/2": error,
                }
            )
        self.assertIn("unavailable", result["issues"][0]["error"])
        self.assertIn("HTTP 503", stderr.getvalue())

    def test_issue_comment_failure_preserves_issue(self):
        api = f"repos/{REPOSITORY}"
        error = subprocess.CalledProcessError(1, "gh", stderr="HTTP 503")
        with redirect_stderr(io.StringIO()):
            result = self.run_main(
                {
                    f"{api}/pulls/1": {"title": "Fix", "body": "#2"},
                    f"{api}/issues/2": {"title": "Bug"},
                    f"{api}/issues/2/comments": error,
                }
            )
        self.assertEqual(result["issues"][0]["title"], "Bug")
        self.assertIn("unavailable", result["issues"][0]["comments_error"])

    def run_main(self, responses):
        def gh(*args):
            response = responses[args[-1]]
            if isinstance(response, Exception):
                raise response
            return response

        stdout = io.StringIO()
        with patch("context.gh", gh), patch.object(
            sys, "argv", ["context.py", REPOSITORY, "1"]
        ), redirect_stdout(stdout):
            main()
        output = stdout.getvalue()
        self.assertGreater(len(output.splitlines()), 1)
        self.assertLess(max(map(len, output.splitlines())), 2000)
        return json.loads(output)

    def test_builds_context_with_linked_issues(self):
        api = f"repos/{REPOSITORY}"
        result = self.run_main(
            {
                f"{api}/pulls/1": {
                    "title": "Fix",
                    "body": "Workaround because of #2. See #3, #4 and #5.",
                    "user": None,
                },
                f"{api}/issues/2": {
                    "title": "Bug",
                    "body": "Must keep the API.",
                    "user": {"login": "maintainer"},
                },
                f"{api}/issues/2/comments": [
                    [{"body": "Agreed", "user": {"login": "a"}}],
                    [{"body": "Later", "user": None}],
                ],
                f"{api}/issues/3": {"title": "PR", "pull_request": {}},
                f"{api}/issues/4": subprocess.CalledProcessError(
                    1, "gh", stderr="HTTP 404"
                ),
                f"{api}/issues/5": {"title": "Empty", "body": None, "user": None},
                f"{api}/issues/5/comments": [[]],
            }
        )
        self.assertEqual(
            result,
            {
                "title": "Fix",
                "author": None,
                "body": "Workaround because of #2. See #3, #4 and #5.",
                "issues": [
                    {
                        "repository": REPOSITORY,
                        "number": 2,
                        "title": "Bug",
                        "author": "maintainer",
                        "body": "Must keep the API.",
                        "comments": [
                            {"author": "a", "body": "Agreed"},
                            {"author": None, "body": "Later"},
                        ],
                    },
                    {
                        "repository": REPOSITORY,
                        "number": 5,
                        "title": "Empty",
                        "author": None,
                        "body": "",
                        "comments": [],
                    },
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
