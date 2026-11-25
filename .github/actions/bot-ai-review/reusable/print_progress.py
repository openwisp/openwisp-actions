"""Print the review's tool calls while it runs.

The events are read from standard input as they are written, so the job log
shows the last command even if the runner is lost before the review ends.
Lines are checked for the provider's credentials like the output of a
finished review: a line containing one is hidden, and nothing is printed
when the credentials cannot be read.
"""

import json
import sys


def read_credentials(path, model):
    """Return the provider tokens, or None when they cannot be checked."""
    try:
        with open(path) as f:
            providers = json.load(f)
    except FileNotFoundError:
        # Copilot is configured with an auth file, other providers may not be.
        return None if model.startswith("github-copilot/") else set()
    except (OSError, ValueError):
        return None
    if not isinstance(providers, dict):
        return None
    tokens = {
        token
        for provider in providers.values()
        if isinstance(provider, dict)
        for token in (provider.get("refresh"), provider.get("access"))
        if isinstance(token, str) and token
    }
    if model.startswith("github-copilot/") and not tokens:
        return None
    return tokens


def describe(event):
    part = event.get("part") or {}
    state = part.get("state") or {}
    inputs = state.get("input") or {}
    target = inputs.get("command") or inputs.get("url", "")
    return f"Tool: {part.get('tool')} ({state.get('status')}) {target}"


def main():
    auth, model = sys.argv[1:3]
    known = set()
    for line in sys.stdin:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "tool_use":
            continue
        # A token can be refreshed during the review, so read the file again.
        tokens = read_credentials(auth, model)
        if tokens is None:
            print("Tool calls are not shown: the credentials could not be read")
            return
        known |= tokens
        text = describe(event)
        if any(token in text for token in known):
            text = "Tool call hidden: it contains a credential"
        print(text, flush=True)


if __name__ == "__main__":
    main()
