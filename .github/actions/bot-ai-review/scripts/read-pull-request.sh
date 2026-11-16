#!/usr/bin/env bash
set -euo pipefail

PR=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER")
HEAD_SHA=$(jq -er '.head.sha' <<<"$PR")
BASE_SHA=$(jq -er '.base.sha' <<<"$PR")
for SHA in "$HEAD_SHA" "$BASE_SHA"; do
  if ! [[ "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
    echo "::error::Invalid commit reference"
    exit 1
  fi
done
echo "head_sha=$HEAD_SHA" >>"$GITHUB_OUTPUT"
echo "base_sha=$BASE_SHA" >>"$GITHUB_OUTPUT"
