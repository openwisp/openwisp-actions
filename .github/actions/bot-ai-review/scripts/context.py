"""Builds the context of a pull request for the review.

Usage: context.py <repository> <number>

- Includes the title, the description and the issues it references.
- Fetches at most MAX_ISSUES OpenWISP issues, so the description cannot
  make the workflow request arbitrary resources.
"""

import json
import re
import subprocess
import sys

MAX_ISSUES = 5
REFERENCE = re.compile(
    r"https://github\.com/(openwisp/[\w.-]+)/issues/(\d+)"
    r"|(?<![\w/.-])(openwisp/[\w.-]+)?#(\d+)\b",
    re.IGNORECASE,
)


def gh(*args):
    result = subprocess.run(
        ["gh", "api", *args], check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def references(body, repository, number):
    found = []
    for match in REFERENCE.finditer(body):
        repo = match.group(1) or match.group(3) or repository
        reference = (repo.lower(), int(match.group(2) or match.group(4)))
        if reference != (repository.lower(), number) and reference not in found:
            found.append(reference)
    return found[:MAX_ISSUES]


def author(item):
    return (item.get("user") or {}).get("login")


def message(item):
    return {"author": author(item), "body": item.get("body") or ""}


def fetch_issue(repository, number):
    try:
        issue = gh(f"repos/{repository}/issues/{number}")
    except subprocess.CalledProcessError:
        return None
    if "pull_request" in issue:
        return None
    pages = gh("--paginate", "--slurp", f"repos/{repository}/issues/{number}/comments")
    return {
        "repository": repository,
        "number": number,
        "title": issue["title"],
        **message(issue),
        "comments": [message(comment) for page in pages for comment in page],
    }


def main():
    repository, number = sys.argv[1], int(sys.argv[2])
    pr = gh(f"repos/{repository}/pulls/{number}")
    body = pr.get("body") or ""
    issues = (
        fetch_issue(*reference) for reference in references(body, repository, number)
    )
    context = {
        "title": pr["title"],
        **message(pr),
        "issues": [issue for issue in issues if issue],
    }
    print(json.dumps(context))


if __name__ == "__main__":
    main()
