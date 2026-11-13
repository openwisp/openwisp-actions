#!/usr/bin/env bash
set -euo pipefail

DIR=$(dirname "$(realpath "$0")")
gh api graphql -F owner="$OWNER" -F name="$NAME" -F number="$PR_NUMBER" \
  -F query=@"$DIR/history.graphql" |
  jq '.data.repository.pullRequest' >"$RUNNER_TEMP/history.json"
