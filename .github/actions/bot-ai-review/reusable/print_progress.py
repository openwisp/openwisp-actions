"""Print the review's tool calls while it runs.

The events of one file are read from standard input as they are written:
commands when they start, recorded by the sandbox shell, or tool calls when
they end, reported by OpenCode. The job log then shows the last command even
if the runner is lost while it runs.
Lines are checked for the provider's credentials like the output of a
finished review: a line is hidden when it contains one, or when the
credentials cannot be read.
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
        for token in (
            provider.get("refresh"),
            provider.get("access"),
            provider.get("key"),
        )
        if isinstance(token, str) and token
    }
    if model.startswith("github-copilot/") and not tokens:
        return None
    return tokens


def describe(event):
    if event.get("type") == "tool_start":
        args = event.get("args") or [""]
        return f"Started: {args[-1]}"
    part = event.get("part") or {}
    state = part.get("state") or {}
    inputs = state.get("input") or {}
    target = inputs.get("command") or inputs.get("url", "")
    return f"Tool: {part.get('tool')} ({state.get('status')}) {target}"


def main():
    auth, model, initial = sys.argv[1:4]
    # The credentials before the review started, which a refresh may replace.
    known = read_credentials(initial, model) or set()
    for line in sys.stdin:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") not in (
            "tool_start",
            "tool_use",
        ):
            continue
        # A token can be refreshed during the review, so read the file again. A
        # refresh can also leave it briefly incomplete: hide only this line then.
        tokens = read_credentials(auth, model)
        if tokens is None:
            text = "Tool call hidden: the credentials could not be read"
        else:
            known |= tokens
            text = describe(event)
            if any(token in text for token in known):
                text = "Tool call hidden: it contains a credential"
        print(text, flush=True)


if __name__ == "__main__":
    main()
