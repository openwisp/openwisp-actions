#!/usr/bin/env bash
# Resolve the requested branches and source commit.
set -e

if [ -n "$COMMIT_SHA" ]; then
  SHA="$COMMIT_SHA"
  COMMIT_MSG=$(gh api "repos/$REPO/git/commits/$SHA" --jq '.message')
  # Read the branch list from the last backport tag on each matching line.
  BRANCHES=$(echo "$COMMIT_MSG" | sed -n 's/.*\[backport[:[:space:]]\+\([^]]*\)\].*/\1/p' |
    tr '\n' ',' | sed 's/,$//')
else
  PR_DATA=$(gh pr view "$PR_NUMBER" --repo "$REPO" --json state,mergeCommit)
  PR_STATE=$(echo "$PR_DATA" | jq -r '.state')
  if [ "$PR_STATE" != "MERGED" ]; then
    echo "PR #$PR_NUMBER is not merged, skipping"
    echo "branches=[]" >> "$GITHUB_OUTPUT"
    echo "sha=" >> "$GITHUB_OUTPUT"
    exit 0
  fi
  SHA=$(echo "$PR_DATA" | jq -r '.mergeCommit.oid')
  # Stop at the first space after the branch list so trailing prose is ignored.
  BRANCHES=$(echo "$COMMENT_BODY" | sed -n 's|.*/backport[[:space:]]\+\([^[:space:]]*\).*|\1|p' |
    tr '\n' ',' | sed 's/,$//')
fi

if [ -z "$BRANCHES" ]; then
  echo "branches=[]" >> "$GITHUB_OUTPUT"
else
  # Quote each branch as a JSON string for the workflow matrix's fromJSON call.
  echo "branches=$(echo "$BRANCHES" | tr ',' '\n' | jq -R . | jq -sc .)" >> "$GITHUB_OUTPUT"
fi
echo "sha=$SHA" >> "$GITHUB_OUTPUT"
