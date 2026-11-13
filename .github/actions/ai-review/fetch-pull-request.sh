#!/usr/bin/env bash
set -euo pipefail

PR_DIR="$RUNNER_TEMP/pr"
git fetch --no-tags origin "refs/pull/$PR_NUMBER/head"
git worktree add --detach "$PR_DIR" "$HEAD_SHA"
git diff "$BASE_SHA...$HEAD_SHA" >"$RUNNER_TEMP/pr.diff"
find "$PR_DIR" -type l -delete
find "$PR_DIR" \( -name .opencode -o -name opencode.json -o -name opencode.jsonc \
  -o -name AGENTS.md -o -name CLAUDE.md -o -name CONTEXT.md \) -prune -exec rm -rf {} +
if [ -f AGENTS.md ]; then
  cp AGENTS.md "$PR_DIR/AGENTS.md"
fi
