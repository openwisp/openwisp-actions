"""Extracts and validates the findings of an AI review.

Usage: extract_findings.py <model-output> <diff> <stage>

- Prints the findings as JSON, or a "review not completed" fallback.
- Keeps only line comments on new-side diff lines, which GitHub accepts.
- Adds a comment pointing to the summary when there are none, because
  Crit only posts reviews with at least one line comment.
"""

import json
import re
import sys

VERDICTS = {
    "review": {
        "Looks good": "comment",
        "Needs changes": "request-changes",
        "May be wrong direction": "request-changes",
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
DIRECTION_VERDICTS = {"May be wrong direction"}
SEVERITIES = ("P1", "P2", "P3")
MAX_COMMENTS = 20
MAX_BODY = 2000
MAX_SUMMARY = 4000
MAX_TITLE = 100
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
HEADING = re.compile(r"\n+(?=#)")
ANCHOR_BODY = "See the review summary."
FALLBACK = {
    "event": "comment",
    "verdict": "Review not completed",
    "summary": "- The model did not return a valid review.",
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


def format_comment(comment, lines):
    if not isinstance(comment, dict):
        return None
    path = comment.get("file")
    line = comment.get("line")
    severity = comment.get("severity")
    title = comment.get("title")
    body = comment.get("body")
    if not (
        isinstance(line, int)
        and not isinstance(line, bool)
        and line in lines.get(path, ())
        and severity in SEVERITIES
        and isinstance(title, str)
        and title.strip()
        and isinstance(body, str)
        and body.strip()
    ):
        return None
    heading = f"**{severity} · {title.strip()[:MAX_TITLE]}**"
    return {
        "file": path,
        "line": line,
        "body": f"{heading}\n\n{body.strip()[:MAX_BODY]}",
    }


def validate(data, lines, verdicts):
    verdict = data.get("verdict")
    title = data.get("title")
    summary = data.get("summary")
    comments = data.get("comments", [])
    if verdict not in verdicts or not isinstance(comments, list):
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(summary, str) or not summary.strip():
        return None
    formatted = (format_comment(comment, lines) for comment in comments[:MAX_COMMENTS])
    return {
        "event": verdicts[verdict],
        "verdict": verdict,
        "title": title.strip()[:MAX_TITLE],
        "summary": HEADING.sub("\n\n", summary.strip())[:MAX_SUMMARY],
        "comments": (
            []
            if verdict in DIRECTION_VERDICTS
            else [comment for comment in formatted if comment]
        ),
    }


def parse_diff(diff):
    lines = {}
    added = []
    unchanged = []
    path = None
    line = 0
    for row in diff.splitlines():
        if row.startswith("diff --git "):
            path = None
            continue
        if row.startswith("+++ "):
            path = row[6:] if row.startswith("+++ b/") else None
            continue
        match = HUNK.match(row)
        if match:
            line = int(match.group(1))
            continue
        if path is None or row.startswith(("-", "\\")):
            continue
        lines.setdefault(path, set()).add(line)
        (added if row.startswith("+") else unchanged).append((path, line))
        line += 1
    anchor = (added or unchanged or [None])[0]
    return lines, anchor


def main():
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        text = ANSI.sub("", f.read())
    with open(sys.argv[2], encoding="utf-8", errors="replace") as f:
        lines, anchor = parse_diff(f.read())
    verdicts = VERDICTS[sys.argv[3]]
    data = find_json(text)
    findings = validate(data, lines, verdicts) if data else None
    findings = findings or dict(FALLBACK)
    if not findings["comments"] and anchor:
        findings["comments"] = [
            {"file": anchor[0], "line": anchor[1], "body": ANCHOR_BODY}
        ]
    print(json.dumps(findings))


if __name__ == "__main__":
    main()
