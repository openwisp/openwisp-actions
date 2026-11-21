#!/usr/bin/env bash
# Select PR titles that can produce a changelog entry.
set -eo pipefail
if echo "$PR_TITLE" | grep -qiE '^\[(feature|fix|change!?)\]'; then
  echo "has_noteworthy=true" >> "$GITHUB_OUTPUT"
fi
