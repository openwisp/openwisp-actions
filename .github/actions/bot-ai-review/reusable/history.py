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
# not mistaken for real blocks.
TOKEN = re.compile(
    # Fenced code ends at a fence at least as long, or at the end of the comment.
    # Lines in quotes start with ">".
    r"(?P<fenced>^[ \t>]*(?P<fence>`{3,}|~{3,}).*?"
    r"(?:^[ \t>]*(?P=fence)[`~]*[ \t]*$|\Z))"
    # Inline code does not cross a blank line.
    r"|(?P<code>(?P<ticks>`+)(?:(?!\n[ \t>]*\n).)*?(?<!`)(?P=ticks)(?!`))"
    r"|<!-- ai-agent-prompt:(?P<marker>start|end) -->"
    r"|(?P<open><details\b[^>]*>[\s>]*<summary\b[^>]*>"
    r"(?P<title>(?:(?!</summary>).)*)</summary\s*>)"
    r"|(?P<tag><(?P<close>/)?details\b[^>]*>)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
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


def without_prompts(body):
    """Removes CodeRabbit's prompts, which can contain example blocks."""
    parts, pos, start, depth = [], 0, None, 0
    for token in TOKEN.finditer(body):
        if token["fenced"] or token["code"]:
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
