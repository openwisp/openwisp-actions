#!/usr/bin/env bash
# Run review commands as the sandbox user in a synchronized working copy.
# Pass command arguments through "$@" so the wrapper does not interpolate them into its shell code.
# OpenCode reports a tool call only once it ends, so record each command before it runs.
# The job log can then show a command that exhausts the runner. This runs as the runner
# user, so the sandbox user cannot change what is recorded.
if [ -n "${AI_REVIEW_STARTS:-}" ]; then
  # Time in milliseconds, like OpenCode's events, to print both in the order they happened.
  # Isolated mode: the working directory can be the pull request, whose modules must not
  # be imported by the runner user.
  python3 -I -c 'import json, sys, time
print(json.dumps({"type": "tool_start", "timestamp": int(time.time() * 1000), "args": sys.argv[1:]}))' \
    "$@" >>"$AI_REVIEW_STARTS" || true
fi
exec sudo -n -H -u reviewer -- /bin/bash -c '
/usr/local/bin/ai-review-sync /tmp/ai-review/pr /tmp/ai-review/run "$HOME/.ai-review-files" || exit 1
case "$PWD/" in
  /tmp/ai-review/pr/*) cd "/tmp/ai-review/run${PWD#/tmp/ai-review/pr}" || exit 1 ;;
esac
exec /bin/bash "$@"' ai-review-shell "$@"
