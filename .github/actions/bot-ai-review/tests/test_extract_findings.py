import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS)

from extract_findings import (  # noqa: E402
    ANCHOR_BODY,
    FALLBACK,
    MAX_COMMENTS,
    VERDICTS,
    find_json,
    main,
    parse_diff,
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
LINES = {"app.py": {1, 2, 3}}


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
            ("review", "May be wrong direction", "request-changes"),
            ("security-review", "No issues found", "comment"),
            ("security-review", "Inconclusive", "comment"),
            ("final-review", "Ready to merge", "approve"),
            ("final-review", "Needs changes", "request-changes"),
        ]
        for stage, verdict, event in cases:
            with self.subTest(stage=stage, verdict=verdict):
                data = {
                    "verdict": verdict,
                    "title": "T",
                    "summary": "S",
                    "comments": [],
                }
                result = validate(data, LINES, VERDICTS[stage])
                self.assertEqual(result["event"], event)

    def test_rejects_verdict_of_another_stage(self):
        data = {
            "verdict": "Ready to merge",
            "title": "T",
            "summary": "S",
            "comments": [],
        }
        self.assertIsNone(validate(data, LINES, VERDICTS["review"]))

    def test_drops_line_comments_when_direction_is_questioned(self):
        data = {
            "verdict": "May be wrong direction",
            "title": "T",
            "summary": "S",
            "comments": [comment()],
        }
        result = validate(data, LINES, VERDICTS["review"])
        self.assertEqual(result["comments"], [])

    def test_rejects_non_string_verdict(self):
        for verdict in ([], {}):
            with self.subTest(verdict=verdict):
                data = {"verdict": verdict, "title": "T", "summary": "S"}
                self.assertIsNone(validate(data, LINES, VERDICTS["review"]))

    def test_rejects_missing_title(self):
        data = {"verdict": "Looks good", "summary": "S", "comments": []}
        self.assertIsNone(validate(data, LINES, VERDICTS["review"]))

    def test_separates_summary_headings(self):
        summary = "##### Addressed\n- None\n##### Outstanding\n- A"
        data = {"verdict": "Needs changes", "title": "T", "summary": summary}
        result = validate(data, LINES, VERDICTS["final-review"])
        self.assertEqual(
            result["summary"], "##### Addressed\n- None\n\n##### Outstanding\n- A"
        )

    def test_rejects_empty_summary(self):
        data = {"verdict": "Looks good", "title": "T", "summary": " ", "comments": []}
        self.assertIsNone(validate(data, LINES, VERDICTS["review"]))

    def test_formats_comment_heading(self):
        data = {
            "verdict": "Needs changes",
            "title": "T",
            "summary": "S",
            "comments": [comment()],
        }
        result = validate(data, LINES, VERDICTS["review"])
        self.assertEqual(result["comments"][0]["body"], "**P2 · Title**\n\nBody")

    def test_drops_invalid_comments(self):
        invalid = [
            comment(file="other.py"),
            comment(file=[]),
            comment(file={}),
            comment(line=0),
            comment(line=9),
            comment(line=True),
            comment(severity="P4"),
            comment(title=""),
            comment(body=" "),
            "not a dict",
        ]
        data = {
            "verdict": "Needs changes",
            "title": "T",
            "summary": "S",
            "comments": invalid,
        }
        result = validate(data, LINES, VERDICTS["review"])
        self.assertEqual(result["comments"], [])

    def test_invalid_comments_do_not_use_up_the_limit(self):
        comments = ["not a dict"] * MAX_COMMENTS + [comment(title="Kept")]
        data = {
            "verdict": "Needs changes",
            "title": "T",
            "summary": "S",
            "comments": comments,
        }
        result = validate(data, LINES, VERDICTS["review"])
        self.assertEqual(len(result["comments"]), 1)
        self.assertIn("Kept", result["comments"][0]["body"])

    def test_lists_findings_outside_the_diff_in_the_summary(self):
        data = {
            "verdict": "Needs changes",
            "title": "T",
            "summary": "S",
            "comments": [
                comment(file="views.py", line=210, severity="P1", title="Bind it"),
                comment(line=True, title="No line"),
            ],
        }
        result = validate(data, LINES, VERDICTS["review"])
        self.assertEqual(result["comments"], [])
        self.assertEqual(
            result["summary"],
            "S\n\n**Other findings:**\n\n"
            "- P1 · `views.py:210` · Bind it: Body\n"
            "- P2 · `app.py` · No line: Body",
        )

    def test_lists_findings_over_the_limit_in_the_summary(self):
        comments = [comment(title=f"T{n}") for n in range(MAX_COMMENTS + 2)]
        data = {
            "verdict": "Needs changes",
            "title": "T",
            "summary": "S",
            "comments": comments,
        }
        result = validate(data, LINES, VERDICTS["review"])
        self.assertEqual(len(result["comments"]), MAX_COMMENTS)
        self.assertTrue(
            result["summary"].endswith(
                f"- P2 · `app.py:2` · T{MAX_COMMENTS}: Body\n"
                f"- P2 · `app.py:2` · T{MAX_COMMENTS + 1}: Body"
            )
        )

    def test_limits_number_of_comments(self):
        comments = [comment() for _ in range(MAX_COMMENTS + 5)]
        data = {
            "verdict": "Needs changes",
            "title": "T",
            "summary": "S",
            "comments": comments,
        }
        result = validate(data, LINES, VERDICTS["review"])
        self.assertEqual(len(result["comments"]), MAX_COMMENTS)


class TestParseDiff(unittest.TestCase):
    def test_returns_new_side_lines_and_first_added_line(self):
        self.assertEqual(parse_diff(DIFF), (LINES, ("app.py", 2)))

    def test_reads_every_file(self):
        diff = DIFF + (
            "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n"
            "@@ -10,2 +10,2 @@\n x\n-y\n+z\n"
        )
        lines, _ = parse_diff(diff)
        self.assertEqual(lines["b.py"], {10, 11})

    def test_anchors_deletions_on_an_unchanged_line(self):
        diff = "--- a/app.py\n+++ b/app.py\n@@ -4,2 +4,1 @@\n keep\n-drop\n"
        self.assertEqual(parse_diff(diff), ({"app.py": {4}}, ("app.py", 4)))

    def test_decodes_quoted_and_spaced_file_names(self):
        cases = [
            ('+++ "b/caf\\303\\251.py"', "café.py"),
            ('+++ "b/tab\\there.py"', "tab\there.py"),
            ('+++ "b/new\\nline.py"', "new\nline.py"),
            ('+++ "b/quote\\"d.py"', 'quote"d.py'),
            ("+++ b/with space.py\t", "with space.py"),
        ]
        for header, name in cases:
            with self.subTest(name=name):
                diff = f"--- /dev/null\n{header}\n@@ -0,0 +1 @@\n+x\n"
                self.assertEqual(parse_diff(diff), ({name: {1}}, (name, 1)))

    def test_has_no_anchor_without_new_side_lines(self):
        changes = {
            "deleted file": "git rm -q old.py",
            "emptied file": ": >old.py",
            "rename only": "git mv old.py new.py",
            "binary only": "printf '\\0\\1' >data.bin",
        }
        for name, change in changes.items():
            with self.subTest(change=name), tempfile.TemporaryDirectory() as repo:
                script = (
                    "git init -q && git config user.email a@b && git config user.name a"
                    " && echo x >old.py && printf '\\0' >data.bin"
                    " && git add . && git commit -qm base"
                    f" && {change} && git add -A && git diff --cached"
                )
                diff = subprocess.run(
                    script,
                    shell=True,
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                self.assertEqual(parse_diff(diff), ({}, None))


class TestMain(unittest.TestCase):
    def run_main(self, output, stage="review"):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, content in (("output.txt", output), ("pr.diff", DIFF)):
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

    def test_falls_back_on_wrong_types(self):
        result = self.run_main('{"verdict": [], "title": "T", "summary": "S"}')
        self.assertEqual(result["verdict"], FALLBACK["verdict"])

    def test_adds_anchor_when_there_are_no_comments(self):
        output = json.dumps(
            {"verdict": "Ready to merge", "title": "T", "summary": "S", "comments": []}
        )
        result = self.run_main(output, stage="final-review")
        self.assertEqual(result["event"], "approve")
        self.assertEqual(result["comments"][0]["body"], ANCHOR_BODY)

    def test_keeps_valid_comments(self):
        output = json.dumps(
            {
                "verdict": "Needs changes",
                "security_perimeter": "NO",
                "title": "T",
                "summary": "S",
                "comments": [comment()],
            }
        )
        result = self.run_main(output)
        self.assertEqual(result["event"], "request-changes")
        self.assertEqual(len(result["comments"]), 1)
        self.assertNotEqual(result["comments"][0]["body"], ANCHOR_BODY)

    def review(self, **decision):
        data = {"verdict": "Looks good", "title": "T", "summary": "S", **decision}
        return self.run_main(json.dumps(data))

    def test_recommends_security_review_when_perimeter_is_affected(self):
        result = self.review(security_perimeter="YES", boundary="Device enrollment")
        self.assertEqual(result["verdict"], "Looks good")
        self.assertTrue(
            result["summary"].endswith(
                "**Security perimeter: YES** (Device enrollment)."
                " Run `/security-review` next."
            )
        )

    def test_recommends_final_review_when_perimeter_is_not_affected(self):
        result = self.review(security_perimeter="NO")
        self.assertEqual(result["verdict"], "Looks good")
        self.assertTrue(
            result["summary"].endswith(
                "**Security perimeter: NO.** A security review is not needed,"
                " run `/final-review` next."
            )
        )

    def test_falls_back_without_a_perimeter_decision(self):
        cases = [
            {},
            {"security_perimeter": "MAYBE"},
            {"security_perimeter": "YES"},
            {"security_perimeter": "YES", "boundary": " "},
            {"security_perimeter": "YES", "boundary": []},
        ]
        for decision in cases:
            with self.subTest(decision=decision):
                result = self.review(**decision)
                self.assertEqual(result["verdict"], FALLBACK["verdict"])

    def test_reports_prompt_injection_without_a_perimeter_decision(self):
        output = json.dumps(
            {
                "verdict": "Prompt injection detected",
                "title": "T",
                "summary": "S",
                "comments": [comment()],
            }
        )
        result = self.run_main(output)
        self.assertEqual(result["event"], "request-changes")
        self.assertEqual(result["summary"], "S")
        self.assertEqual(len(result["comments"]), 1)
        self.assertNotEqual(result["comments"][0]["body"], ANCHOR_BODY)

    def test_reports_prompt_injection_in_every_stage(self):
        output = json.dumps(
            {
                "verdict": "Prompt injection detected",
                "title": "T",
                "summary": "S",
                "comments": [comment()],
            }
        )
        for stage in ("security-review", "final-review"):
            with self.subTest(stage=stage):
                result = self.run_main(output, stage=stage)
                self.assertEqual(result["verdict"], "Prompt injection detected")
                self.assertEqual(result["event"], "request-changes")
                self.assertEqual(len(result["comments"]), 1)

    def test_other_stages_do_not_need_a_perimeter_decision(self):
        for stage, verdict in (
            ("security-review", "No issues found"),
            ("final-review", "Ready to merge"),
        ):
            with self.subTest(stage=stage):
                output = json.dumps({"verdict": verdict, "title": "T", "summary": "S"})
                result = self.run_main(output, stage=stage)
                self.assertEqual(result["verdict"], verdict)
                self.assertEqual(result["summary"], "S")


if __name__ == "__main__":
    unittest.main()
