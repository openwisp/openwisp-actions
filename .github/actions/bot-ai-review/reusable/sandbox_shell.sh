#!/usr/bin/env bash
# Run review commands as the sandbox user in a synchronized working copy.
# Pass command arguments through "$@" so the wrapper does not interpolate them into its shell code.
exec sudo -n -H -u reviewer -- /bin/bash -c '
/usr/local/bin/ai-review-sync /tmp/ai-review/pr /tmp/ai-review/run "$HOME/.ai-review-files" || exit 1
case "$PWD/" in
  /tmp/ai-review/pr/*) cd "/tmp/ai-review/run${PWD#/tmp/ai-review/pr}" || exit 1 ;;
esac
exec /bin/bash "$@"' ai-review-shell "$@"
