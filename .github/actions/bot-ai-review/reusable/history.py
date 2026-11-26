"""Builds the full discussion of a pull request for the review.

Usage: history.py <directory>

- Reads every page fetched by fetch_history.sh, so no discussion is left out.
- Groups inline comments into threads with their resolved state.
- Removes the prompts that review bots such as CodeRabbit add for AI
  agents, so the reviewer does not mistake them for prompt injection.
"""

import json
import os
import re
import sys

AGENT_PROMPT = re.compile(
    r"<details>\s*<summary>(?:<[^>]*>|[^\w<])*"
    r"Prompt for (?:all review comments with )?AI agents\s*</summary>.*?</details>",
    re.IGNORECASE | re.DOTALL,
)
# Read CodeRabbit's comments as Markdown, so that markup shown in code is
# not mistaken for real blocks. Code is found from runs of backticks or
# tildes, without backtracking, so long runs cannot slow the review down.
TOKEN = re.compile(
    r"(?P<run>`+|~{3,})"
    r"|<!-- ai-agent-prompt:(?P<marker>start|end) -->"
    r"|(?P<open><details\b[^>]*>[\s>]*<summary\b[^>]*>"
    r"(?P<title>(?:(?!</summary>)[^\n]){0,1000})</summary\s*>)"
    r"|(?P<tag><(?P<close>/)?details\b[^>]*>)",
    re.IGNORECASE,
)
# CodeRabbit renames its prompts, but gives them a robot icon that its findings
# do not use.
PROMPT_TITLE = re.compile(
    r"<(?:img|source)\b[^>]*[/\"']bot(?:-dark)?\.svg\b"
    r"|\N{ROBOT FACE}"
    r"|^(?:<[^>]*>|[^\w<])*Prompt for (?:all review comments with )?AI agents\s*$",
    re.IGNORECASE,
)


def load(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as f:
        return json.load(f)


def flatten(pages):
    return [item for page in pages for item in page]


def author(item):
    return (item.get("user") or {}).get("login")


def at_line_start(body, token):
    # Lines in quotes start with ">".
    start = token.start()
    line = body.rfind("\n", 0, start) + 1
    return not body[line:start].strip(" \t>")


def inline_code_ends(tokens):
    """Maps each run of backticks to the next run of the same length."""
    ends, following = {}, {}
    for index in range(len(tokens) - 1, -1, -1):
        run = tokens[index]["run"]
        if run and run[0] == "`":
            ends[index] = following.get(run)
            following[run] = index
    return ends


def without_prompts(body):
    """Removes CodeRabbit's prompts, which can contain example blocks."""
    tokens = list(TOKEN.finditer(body))
    inline_ends = inline_code_ends(tokens)
    parts, pos, start, depth = [], 0, None, 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if run := token["run"]:
            if len(run) >= 3 and at_line_start(body, token):
                # A fence closes at a fence at least as long, or at the end.
                while index < len(tokens) and not (
                    (tokens[index]["run"] or "").startswith(run)
                    and at_line_start(body, tokens[index])
                ):
                    index += 1
                index += 1
            elif inline_ends.get(index - 1) is not None:
                index = inline_ends[index - 1] + 1
            continue
        if start is None:
            if token["marker"] == "start":
                # A marked prompt ends at its end marker.
                start, depth = token.start(), None
            elif token["open"] and PROMPT_TITLE.search(token["title"]):
                start, depth = token.start(), 1
            continue
        if depth is None:
            done = token["marker"] == "end"
        else:
            if token["open"] or (token["tag"] and not token["close"]):
                depth += 1
            elif token["close"]:
                depth -= 1
            done = depth == 0
        if done:
            parts.append(body[pos:start])
            pos, start = token.end(), None
    parts.append(body[pos:])
    return "".join(parts)


def message(item):
    body = item["body"]
    # The markers and the robot icon are CodeRabbit's: other bots can use them
    # for findings.
    if author(item) == "coderabbitai[bot]":
        body = without_prompts(body)
    elif (item.get("user") or {}).get("type") == "Bot":
        body = AGENT_PROMPT.sub("", body)
    return {"author": author(item), "body": body}


def build(comments, reviews, review_comments, threads):
    states = {
        thread["comments"]["nodes"][0]["fullDatabaseId"]: thread
        for thread in threads
        if thread["comments"]["nodes"]
    }
    grouped = {}
    for comment in review_comments:
        root = comment.get("in_reply_to_id") or comment["id"]
        grouped.setdefault(root, []).append(comment)
    return {
        "comments": [message(comment) for comment in comments],
        "reviews": [
            {**message(review), "state": review["state"], "commit": review["commit_id"]}
            for review in reviews
        ],
        "threads": [
            {
                "resolved": states.get(str(root), {}).get("isResolved"),
                "outdated": states.get(str(root), {}).get("isOutdated"),
                "path": replies[0]["path"],
                "line": replies[0]["line"],
                "comments": [message(reply) for reply in replies],
            }
            for root, replies in grouped.items()
        ],
    }


def main():
    directory = sys.argv[1]
    threads = [
        node
        for page in load(directory, "threads.json")
        for node in page["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    ]
    history = build(
        flatten(load(directory, "comments.json")),
        flatten(load(directory, "reviews.json")),
        flatten(load(directory, "review-comments.json")),
        threads,
    )
    print(json.dumps(history, indent=1))


if __name__ == "__main__":
    main()
