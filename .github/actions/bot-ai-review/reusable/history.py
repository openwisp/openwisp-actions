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
# CodeRabbit marks some of its prompts for AI agents.
MARKED_PROMPT = re.compile(
    r"<!-- ai-agent-prompt:start -->.*?<!-- ai-agent-prompt:end -->", re.DOTALL
)
# CodeRabbit renames its other prompts, but gives them a robot icon that its
# findings do not use. The title cannot cross "</summary>", so a block that
# holds findings and a prompt keeps its findings.
CODERABBIT_PROMPT = re.compile(
    # Blocks in quotes have ">" at the start of each line.
    r"<details>[\s>]*<summary>(?:"
    r"(?:(?!</summary>).)*?(?:\bbot(?:-dark)?\.svg\b|\N{ROBOT FACE})(?:(?!</summary>).)*"
    r"|(?:<[^>]*>|[^\w<])*Prompt for (?:all review comments with )?AI agents\s*"
    r")</summary>",
    re.IGNORECASE | re.DOTALL,
)
# Tags shown as examples in code do not open or close blocks.
DETAILS_TAG = re.compile(
    r"```.*?```|`[^`\n]*`|<(/?)details>", re.IGNORECASE | re.DOTALL
)


def load(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as f:
        return json.load(f)


def flatten(pages):
    return [item for page in pages for item in page]


def author(item):
    return (item.get("user") or {}).get("login")


def without_prompts(body):
    # A prompt can contain example blocks, so remove up to its own closing tag.
    while match := CODERABBIT_PROMPT.search(body):
        depth = 1
        for tag in DETAILS_TAG.finditer(body, match.end()):
            if tag.group(1) is None:
                continue
            depth += -1 if tag.group(1) else 1
            if not depth:
                start, end = match.start(), tag.end()
                body = body[:start] + body[end:]
                break
        else:
            return body
    return body


def message(item):
    body = item["body"]
    # The markers and the robot icon are CodeRabbit's: other bots can use them
    # for findings.
    if author(item) == "coderabbitai[bot]":
        body = without_prompts(MARKED_PROMPT.sub("", body))
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
