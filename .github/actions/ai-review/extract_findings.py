"""Extracts and validates the findings of an AI review.

Usage: extract_findings.py <model-output> <changed-files> <diff> <stage>

Prints the validated findings as JSON. When the model output does not
contain valid findings, prints a comment review explaining that the
review could not be completed.

Crit only posts reviews which contain at least one line comment, so
findings without line comments get one on the first added line of the
diff, pointing to the review summary.
"""

import json
import re
import sys

VERDICTS = {
    "review": {
        "Looks good": "comment",
        "Needs changes": "request-changes",
        "Wrong direction": "request-changes",
    },
    "security-review": {
        "No issues found": "approve",
        "Issues found": "request-changes",
        "Inconclusive": "comment",
    },
    "final-review": {
        "Ready to merge": "approve",
        "Needs changes": "request-changes",
        "Inconclusive": "comment",
    },
}
SEVERITIES = ("P1", "P2", "P3")
MAX_COMMENTS = 20
MAX_BODY = 2000
MAX_SUMMARY = 4000
MAX_TITLE = 100
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
ANCHOR_BODY = "See the review summary."
FALLBACK = {
    "event": "comment",
    "verdict": "Review not completed",
    "summary": "The review could not be completed: the model output was not valid.",
    "comments": [],
}


def find_json(text):
    decoder = json.JSONDecoder(strict=False)
    for start in reversed([m.start() for m in re.finditer(r"\{", text)]):
        try:
            data, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "verdict" in data:
            return data
    return None


def validate(data, changed_files, verdicts):
    verdict = data.get("verdict")
    summary = data.get("summary")
    comments = data.get("comments", [])
    if verdict not in verdicts:
        return None
    if not isinstance(summary, str) or not summary.strip():
        return None
    if not isinstance(comments, list):
        return None
    valid_comments = []
    for comment in comments[:MAX_COMMENTS]:
        if not isinstance(comment, dict):
            continue
        path = comment.get("file")
        line = comment.get("line")
        severity = comment.get("severity")
        title = comment.get("title")
        body = comment.get("body")
        if (
            path in changed_files
            and isinstance(line, int)
            and not isinstance(line, bool)
            and line > 0
            and severity in SEVERITIES
            and isinstance(title, str)
            and title.strip()
            and isinstance(body, str)
            and body.strip()
        ):
            heading = f"**{severity} · {title.strip()[:MAX_TITLE]}**"
            valid_comments.append(
                {
                    "file": path,
                    "line": line,
                    "body": f"{heading}\n\n{body.strip()[:MAX_BODY]}",
                }
            )
    return {
        "event": verdicts[verdict],
        "verdict": verdict,
        "summary": summary.strip()[:MAX_SUMMARY],
        "comments": valid_comments,
    }


def first_added_line(diff):
    path = None
    line = 0
    for row in diff.splitlines():
        if row.startswith("+++ "):
            path = row[6:] if row.startswith("+++ b/") else None
            continue
        match = HUNK.match(row)
        if match:
            line = int(match.group(1))
            continue
        if path is None or row.startswith(("---", "\\")):
            continue
        if row.startswith("+"):
            return path, line
        if not row.startswith("-"):
            line += 1
    return None


def main():
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        text = ANSI.sub("", f.read())
    with open(sys.argv[2], encoding="utf-8") as f:
        changed_files = {line.strip() for line in f if line.strip()}
    with open(sys.argv[3], encoding="utf-8", errors="replace") as f:
        anchor = first_added_line(f.read())
    verdicts = VERDICTS[sys.argv[4]]
    data = find_json(text)
    findings = validate(data, changed_files, verdicts) if data else None
    findings = findings or dict(FALLBACK)
    if not findings["comments"] and anchor:
        findings["comments"] = [
            {"file": anchor[0], "line": anchor[1], "body": ANCHOR_BODY}
        ]
    print(json.dumps(findings))


if __name__ == "__main__":
    main()
