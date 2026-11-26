"""Builds the full discussion of a pull request for the review.

Usage: history.py <directory>

- Reads every page fetched by fetch_history.sh, so no discussion is left out.
- Groups inline comments into threads with their resolved state.
- Removes the prompts that review bots such as CodeRabbit add for AI
  agents, so the reviewer does not mistake them for prompt injection.
- Leaves out people's comments that only ask CodeRabbit to resolve its
  threads or run one of its commands. They are for CodeRabbit, not for the
  review, and the reviewer would mistake them for prompt injection.
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
# findings do not use. Innermost blocks only, so a block that holds findings
# and a prompt keeps its findings.
DETAILS = re.compile(
    # Blocks in quotes have ">" at the start of each line.
    r"<details>[\s>]*<summary>((?:(?!</summary>).)*)</summary>"
    r"((?:(?!<details>|</details>).)*)</details>",
    re.IGNORECASE | re.DOTALL,
)
ROBOT_ICON = re.compile(r"\bbot(?:-dark)?\.svg\b|\N{ROBOT FACE}")

# CodeRabbit runs a command only when it is the whole comment. None of these approve.
COMMAND = re.compile(
    r"\s*@coderabbitai\s+(?:full review|review|resolve|pause|resume|summary|help"
    r"|configuration|run pre-merge checks)\s*",
    re.IGNORECASE,
)
# A single sentence that asks CodeRabbit to resolve its threads.
RESOLVE = re.compile(
    r"\s*@coderabbitai\b[^.!?\n]*\b(?:resolve|mark\b[^.!?\n]*\bas resolved)\b"
    r"[^.!?\n]*[.!?]?\s*",
    re.IGNORECASE,
)
APPROVE = re.compile(r"\bapprov", re.IGNORECASE)


def load(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as f:
        return json.load(f)


def flatten(pages):
    return [item for page in pages for item in page]


def author(item):
    return (item.get("user") or {}).get("login")


def for_coderabbit(item):
    body = item.get("body") or ""
    # CodeRabbit mentions itself in its own comments, which contain its findings.
    # Requests for approval are kept, so the reviewer still checks them for
    # prompt injection.
    if (item.get("user") or {}).get("type") == "Bot" or APPROVE.search(body):
        return False
    return bool(COMMAND.fullmatch(body) or RESOLVE.fullmatch(body))


def agent_prompt(match):
    return "" if ROBOT_ICON.search(match.group(1)) else match.group(0)


def message(item):
    body = item["body"]
    if (item.get("user") or {}).get("type") == "Bot":
        body = AGENT_PROMPT.sub("", MARKED_PROMPT.sub("", body))
        body = DETAILS.sub(agent_prompt, body)
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
        "comments": [
            message(comment) for comment in comments if not for_coderabbit(comment)
        ],
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
                "comments": [
                    message(reply) for reply in replies if not for_coderabbit(reply)
                ],
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
