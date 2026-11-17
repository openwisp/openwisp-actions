"""Extracts and validates the findings of an AI review.

Usage: extract_findings.py <model-output> <diff> <stage>

- Prints the findings as JSON, or a "review not completed" fallback.
- Keeps only line comments on new-side diff lines, which GitHub accepts,
  and lists the other findings in the summary instead of dropping them.
- Adds a comment pointing to the summary when there are none, because
  Crit only posts reviews with at least one line comment.
"""

import ast
import json
import re
import sys

VERDICTS = {
    "review": {
        "Looks good": "comment",
        "Needs changes": "request-changes",
        "May be wrong direction": "request-changes",
        "Prompt injection detected": "request-changes",
    },
    "security-review": {
        "No issues found": "comment",
        "Issues found": "request-changes",
        "Inconclusive": "comment",
        "Prompt injection detected": "request-changes",
    },
    "final-review": {
        "Ready to merge": "approve",
        "Needs changes": "request-changes",
        "Inconclusive": "comment",
        "Prompt injection detected": "request-changes",
    },
}
DIRECTION_VERDICTS = {"May be wrong direction"}
INJECTION = "Prompt injection detected"
SEVERITIES = ("P1", "P2", "P3")
MAX_COMMENTS = 20
MAX_BODY = 2000
MAX_SUMMARY = 4000
MAX_TITLE = 100
MAX_LEFTOVER_BODY = 500
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
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


def parse_finding(comment):
    if not isinstance(comment, dict):
        return None
    path = comment.get("file")
    line = comment.get("line")
    severity = comment.get("severity")
    title = comment.get("title")
    body = comment.get("body")
    if not (
        isinstance(path, str)
        and path.strip()
        and severity in SEVERITIES
        and isinstance(title, str)
        and title.strip()
        and isinstance(body, str)
        and body.strip()
    ):
        return None
    if not isinstance(line, int) or isinstance(line, bool):
        line = None
    return {
        "file": path,
        "line": line,
        "severity": severity,
        "title": title.strip()[:MAX_TITLE],
        "body": body.strip(),
    }


def format_comment(finding):
    heading = f"**{finding['severity']} · {finding['title']}**"
    return {
        "file": finding["file"],
        "line": finding["line"],
        "body": f"{heading}\n\n{finding['body'][:MAX_BODY]}",
    }


def format_leftovers(findings):
    if not findings:
        return ""
    rows = []
    for finding in findings[:MAX_COMMENTS]:
        location = finding["file"]
        if finding["line"] is not None:
            location += f":{finding['line']}"
        body = " ".join(finding["body"].split())[:MAX_LEFTOVER_BODY]
        rows.append(
            f"- {finding['severity']} · `{location}` · {finding['title']}: {body}"
        )
    return "\n\n**Other findings:**\n\n" + "\n".join(rows)


def validate(data, lines, verdicts):
    verdict = data.get("verdict")
    title = data.get("title")
    summary = data.get("summary")
    comments = data.get("comments", [])
    if not isinstance(verdict, str) or verdict not in verdicts:
        return None
    if not isinstance(comments, list):
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(summary, str) or not summary.strip():
        return None
    summary = HEADING.sub("\n\n", summary.strip())[:MAX_SUMMARY]
    posted = []
    leftovers = []
    if verdict not in DIRECTION_VERDICTS:
        for finding in filter(None, map(parse_finding, comments)):
            in_diff = finding["line"] in lines.get(finding["file"], ())
            if in_diff and len(posted) < MAX_COMMENTS:
                posted.append(format_comment(finding))
            else:
                leftovers.append(finding)
    return {
        "event": verdicts[verdict],
        "verdict": verdict,
        "title": title.strip()[:MAX_TITLE],
        "summary": summary + format_leftovers(leftovers),
        "comments": posted,
    }


def perimeter(data):
    decision = data.get("security_perimeter")
    boundary = data.get("boundary")
    if decision == "NO":
        return (
            "\n\n**Security perimeter: NO.** A security review is not needed,"
            " run `/final-review` next."
        )
    if decision == "YES" and isinstance(boundary, str) and boundary.strip():
        return (
            f"\n\n**Security perimeter: YES** ({boundary.strip()[:MAX_TITLE]})."
            " Run `/security-review` next."
        )
    return None


def unquote(name):
    if name.startswith('"'):
        try:
            return ast.literal_eval("b" + name).decode("utf-8", "replace")
        except (SyntaxError, ValueError):
            return None
    return name


def parse_diff(diff):
    lines = {}
    added = []
    unchanged = []
    path = None
    line = 0
    old_remaining = new_remaining = 0
    for row in diff.splitlines():
        if row.startswith("diff --git "):
            path = None
            old_remaining = new_remaining = 0
            continue
        if not old_remaining and not new_remaining and row.startswith("+++ "):
            name = unquote(row[4:].rstrip("\t"))
            path = name[2:] if name and name.startswith("b/") else None
            continue
        match = HUNK.match(row)
        if match:
            old_remaining = int(match.group(1) or "1")
            line = int(match.group(2))
            new_remaining = int(match.group(3) or "1")
            continue
        if not old_remaining and not new_remaining:
            continue
        if row.startswith((" ", "-")):
            old_remaining -= 1
        if row.startswith((" ", "+")):
            new_remaining -= 1
            if path is not None:
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
    stage = sys.argv[3]
    data = find_json(text)
    findings = validate(data, lines, VERDICTS[stage]) if data else None
    if findings and stage == "review" and findings["verdict"] != INJECTION:
        note = perimeter(data)
        findings = {**findings, "summary": findings["summary"] + note} if note else None
    findings = findings or dict(FALLBACK)
    if not findings["comments"] and anchor:
        findings["comments"] = [
            {"file": anchor[0], "line": anchor[1], "body": ANCHOR_BODY}
        ]
    print(json.dumps(findings))


if __name__ == "__main__":
    main()
