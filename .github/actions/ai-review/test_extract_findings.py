import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extract_findings import (  # noqa: E402
    ANCHOR_BODY,
    FALLBACK,
    MAX_COMMENTS,
    VERDICTS,
    find_json,
    first_added_line,
    main,
    validate,
)

DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 import os
+import sys
 print(os.name)
"""


def comment(**overrides):
    data = {
        "file": "app.py",
        "line": 2,
        "severity": "P2",
        "title": "Title",
        "body": "Body",
    }
    data.update(overrides)
    return data


class TestFindJson(unittest.TestCase):
    def test_finds_last_object_with_verdict(self):
        text = 'log {"other": 1} {"verdict": "first"} noise {"verdict": "last"}'
        self.assertEqual(find_json(text), {"verdict": "last"})

    def test_accepts_raw_newlines_in_strings(self):
        text = '{"verdict": "Ready to merge", "summary": "Addressed:\n- x"}'
        self.assertEqual(find_json(text)["summary"], "Addressed:\n- x")

    def test_returns_none_without_findings(self):
        self.assertIsNone(find_json("no json here"))


class TestValidate(unittest.TestCase):
    def test_maps_verdict_to_event_per_stage(self):
        cases = [
            ("review", "Looks good", "comment"),
            ("review", "Wrong direction", "request-changes"),
            ("security-review", "No issues found", "approve"),
            ("security-review", "Inconclusive", "comment"),
            ("final-review", "Ready to merge", "approve"),
            ("final-review", "Needs changes", "request-changes"),
        ]
        for stage, verdict, event in cases:
            with self.subTest(stage=stage, verdict=verdict):
                data = {"verdict": verdict, "summary": "S", "comments": []}
                result = validate(data, {"app.py"}, VERDICTS[stage])
                self.assertEqual(result["event"], event)

    def test_rejects_verdict_of_another_stage(self):
        data = {"verdict": "Ready to merge", "summary": "S", "comments": []}
        self.assertIsNone(validate(data, {"app.py"}, VERDICTS["review"]))

    def test_rejects_empty_summary(self):
        data = {"verdict": "Looks good", "summary": " ", "comments": []}
        self.assertIsNone(validate(data, {"app.py"}, VERDICTS["review"]))

    def test_formats_comment_heading(self):
        data = {"verdict": "Needs changes", "summary": "S", "comments": [comment()]}
        result = validate(data, {"app.py"}, VERDICTS["review"])
        self.assertEqual(result["comments"][0]["body"], "**P2 · Title**\n\nBody")

    def test_drops_invalid_comments(self):
        invalid = [
            comment(file="other.py"),
            comment(line=0),
            comment(line=True),
            comment(severity="P4"),
            comment(title=""),
            comment(body=" "),
            "not a dict",
        ]
        data = {"verdict": "Needs changes", "summary": "S", "comments": invalid}
        result = validate(data, {"app.py"}, VERDICTS["review"])
        self.assertEqual(result["comments"], [])

    def test_limits_number_of_comments(self):
        comments = [comment() for _ in range(MAX_COMMENTS + 5)]
        data = {"verdict": "Needs changes", "summary": "S", "comments": comments}
        result = validate(data, {"app.py"}, VERDICTS["review"])
        self.assertEqual(len(result["comments"]), MAX_COMMENTS)


class TestFirstAddedLine(unittest.TestCase):
    def test_returns_first_added_line(self):
        self.assertEqual(first_added_line(DIFF), ("app.py", 2))

    def test_skips_deleted_files(self):
        diff = "--- a/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
        self.assertIsNone(first_added_line(diff))


class TestMain(unittest.TestCase):
    def run_main(self, output, stage="review"):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, content in (
                ("output.txt", output),
                ("files.txt", "app.py\n"),
                ("pr.diff", DIFF),
            ):
                path = os.path.join(directory, name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                paths.append(path)
            stdout = io.StringIO()
            with patch.object(sys, "argv", ["extract_findings.py", *paths, stage]):
                with redirect_stdout(stdout):
                    main()
        return json.loads(stdout.getvalue())

    def test_falls_back_on_invalid_output(self):
        result = self.run_main("\x1b[31mError\x1b[0m")
        self.assertEqual(result["verdict"], FALLBACK["verdict"])
        self.assertEqual(result["event"], "comment")
        self.assertEqual(
            result["comments"],
            [{"file": "app.py", "line": 2, "body": ANCHOR_BODY}],
        )

    def test_adds_anchor_when_there_are_no_comments(self):
        output = json.dumps(
            {"verdict": "No issues found", "summary": "S", "comments": []}
        )
        result = self.run_main(output, stage="security-review")
        self.assertEqual(result["event"], "approve")
        self.assertEqual(result["comments"][0]["body"], ANCHOR_BODY)

    def test_keeps_valid_comments(self):
        output = json.dumps(
            {"verdict": "Needs changes", "summary": "S", "comments": [comment()]}
        )
        result = self.run_main(output)
        self.assertEqual(result["event"], "request-changes")
        self.assertEqual(len(result["comments"]), 1)
        self.assertNotEqual(result["comments"][0]["body"], ANCHOR_BODY)


if __name__ == "__main__":
    unittest.main()
