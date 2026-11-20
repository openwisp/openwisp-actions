#!/usr/bin/env bash
# Fetch the approved comparison as data and prepare the generator's git wrapper.
set -euo pipefail
if ! [[ "$APPROVED_HEAD_SHA" =~ ^[0-9a-f]{40}$ && "$APPROVED_BASE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::Invalid approved pull request reference"
  exit 1
fi
COMPARE="repos/$REPOSITORY/compare/$APPROVED_BASE_SHA...$APPROVED_HEAD_SHA?per_page=100"
gh api "$COMPARE" > "$RUNNER_TEMP/changelog-comparison.json"
TOTAL_COMMITS=$(jq -er '.total_commits' "$RUNNER_TEMP/changelog-comparison.json")
COMMIT_COUNT=$(jq -er '.commits | length' "$RUNNER_TEMP/changelog-comparison.json")
FILE_COUNT=$(jq -er '.files | length' "$RUNNER_TEMP/changelog-comparison.json")
if [ "$TOTAL_COMMITS" -ne "$COMMIT_COUNT" ] || [ "$FILE_COUNT" -ge 300 ]; then
  echo "::error::GitHub returned an incomplete pull request comparison"
  exit 1
fi
gh api -H 'Accept: application/vnd.github.diff' "$COMPARE" > "$RUNNER_TEMP/changelog-generator.diff"
jq -r '.commits | reverse | .[] | "\(.sha[0:7]) \(.commit.message | split("\n")[0])"' \
  "$RUNNER_TEMP/changelog-comparison.json" > "$RUNNER_TEMP/changelog-generator.commits"
cp "$(dirname "${BASH_SOURCE[0]}")/git-wrapper.sh" "$RUNNER_TEMP/git"
chmod +x "$RUNNER_TEMP/git"
