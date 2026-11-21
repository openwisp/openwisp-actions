#!/usr/bin/env bash
# Verify that artifact metadata refers to the PR from the triggering run.
set -euo pipefail
PR=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER")
HEAD_SHA=$(jq -er '.head.sha' <<< "$PR")
BASE_REPOSITORY=$(jq -er '.base.repo.full_name' <<< "$PR")
if [ "$HEAD_SHA" != "$EXPECTED_HEAD_SHA" ] || [ "$BASE_REPOSITORY" != "$REPOSITORY" ]; then
  echo "::error::Metadata PR does not match the triggering review run"
  exit 1
fi
echo "head_sha=$HEAD_SHA" >> "$GITHUB_OUTPUT"
