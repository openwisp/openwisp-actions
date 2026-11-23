#!/usr/bin/env bash
# Reject a review if the pull request changed or closed before it starts.
set -euo pipefail

PR=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER" --jq '.state, .head.sha')
mapfile -t FIELDS <<<"$PR"
if [ "${FIELDS[0]:-}" != open ] || [ "${FIELDS[1]:-}" != "$HEAD_SHA" ]; then
  echo "::error::The pull request changed or closed; request another review"
  exit 1
fi
