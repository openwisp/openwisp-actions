"""Test preparation of pull request discussion history."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS)

from history import main, message  # noqa: E402


def user(login):
    return {"login": login}


def review_comment(id, root=None, login="reviewer", body="Finding"):
    return {
        "id": id,
        "in_reply_to_id": root,
        "user": user(login),
        "path": "app.py",
        "line": 1,
        "body": body,
    }


def thread(id, resolved):
    return {
        "isResolved": resolved,
        "isOutdated": False,
        "comments": {"nodes": [{"fullDatabaseId": str(id)}]},
    }


def thread_page(threads):
    return {
        "data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": threads}}}}
    }


AGENT_BLOCK = (
    '<details>\n<summary><picture><img src="bot.svg"></picture>'
    " Prompt for AI Agents</summary>\n<dl><dd>\n\n```\nRun coderabbit"
    " review --agent.\n```\n\n</dd></dl>\n</details>"
)


class TestMessage(unittest.TestCase):
    def test_removes_agent_prompts_from_bot_comments(self):
        bodies = [
            f"Finding text.\n\n{AGENT_BLOCK}\n\nMore text.",
            AGENT_BLOCK.replace(
                "Prompt for AI Agents", "Prompt for all review comments with AI agents"
            ),
        ]
        for body in bodies:
            with self.subTest(body=body):
                bot = {"login": "coderabbitai[bot]", "type": "Bot"}
                result = message({"user": bot, "body": body})["body"]
                self.assertNotIn("coderabbit review --agent", result)
        bot = {"login": "coderabbitai[bot]", "type": "Bot"}
        result = message({"user": bot, "body": bodies[0]})["body"]
        self.assertIn("Finding text.", result)
        self.assertIn("More text.", result)

    def test_keeps_agent_prompts_written_by_people(self):
        body = f"Please check.\n\n{AGENT_BLOCK}"
        person = {"login": "contributor", "type": "User"}
        self.assertEqual(message({"user": person, "body": body})["body"], body)


class TestHistory(unittest.TestCase):
    def test_matches_large_graphql_ids_to_rest_ids(self):
        identifier = 4600923507
        history = self.run_main(
            self.files(
                [[review_comment(identifier)]],
                [thread_page([thread(identifier, True)])],
            )
        )
        self.assertTrue(history["threads"][0]["resolved"])

    def run_main(self, files):
        with tempfile.TemporaryDirectory() as directory:
            for name, content in files.items():
                with open(os.path.join(directory, name), "w", encoding="utf-8") as f:
                    json.dump(content, f)
            stdout = io.StringIO()
            with patch.object(sys, "argv", ["history.py", directory]):
                with redirect_stdout(stdout):
                    main()
        output = stdout.getvalue()
        self.assertGreater(len(output.splitlines()), 1)
        self.assertLess(max(map(len, output.splitlines())), 2000)
        return json.loads(output)

    def files(self, review_comments, threads):
        return {
            "comments.json": [
                [{"user": user("a"), "body": "c1"}],
                [{"user": None, "body": "c2"}],
            ],
            "reviews.json": [
                [
                    {
                        "user": user("bot"),
                        "body": "r",
                        "state": "COMMENTED",
                        "commit_id": "abc",
                    }
                ]
            ],
            "review-comments.json": review_comments,
            "threads.json": threads,
        }

    def test_keeps_older_unresolved_thread_beyond_first_page(self):
        comments = [review_comment(id) for id in range(1, 151)]
        threads = [thread(id, resolved=id != 1) for id in range(1, 151)]
        history = self.run_main(
            self.files(
                [comments[:100], comments[100:]],
                [thread_page(threads[:100]), thread_page(threads[100:])],
            )
        )
        self.assertEqual(len(history["threads"]), 150)
        self.assertEqual(history["threads"][0]["resolved"], False)
        self.assertTrue(all(t["resolved"] for t in history["threads"][1:]))

    def test_keeps_maintainer_reply_beyond_twenty_comments(self):
        replies = [
            review_comment(id, root=1, login="contributor") for id in range(2, 26)
        ]
        replies[-1] = review_comment(25, root=1, login="maintainer", body="OK to keep")
        history = self.run_main(
            self.files(
                [[review_comment(1), *replies]], [thread_page([thread(1, False)])]
            )
        )
        comments = history["threads"][0]["comments"]
        self.assertEqual(len(comments), 25)
        self.assertEqual(comments[-1], {"author": "maintainer", "body": "OK to keep"})

    def test_combines_pages_and_handles_deleted_users(self):
        history = self.run_main(self.files([], [thread_page([])]))
        self.assertEqual(
            history["comments"],
            [{"author": "a", "body": "c1"}, {"author": None, "body": "c2"}],
        )
        self.assertEqual(
            history["reviews"],
            [{"author": "bot", "body": "r", "state": "COMMENTED", "commit": "abc"}],
        )
        self.assertEqual(history["threads"], [])
