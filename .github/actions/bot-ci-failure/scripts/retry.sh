#!/usr/bin/env bash
# Retry transient failures at most three times per commit.
set -eo pipefail
MAX_RETRIES=3
MARKER="<!-- ci-transient-retry $HEAD_SHA -->"
# gh --jq cannot pass jq's --arg, so count the exact marker with grep.
RETRY_COUNT=$(gh pr view "$PR_NUM" --repo "$REPO" --json comments \
  --jq '.comments[].body' 2>/dev/null \
  | grep -cF "$MARKER" || echo "0")
if ! [[ "$RETRY_COUNT" =~ ^[0-9]+$ ]]; then
  RETRY_COUNT=0
fi
echo "Previous retries: $RETRY_COUNT"
if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
  echo "Max retries ($MAX_RETRIES) reached; skipping."
  echo "retried=false" >> "$GITHUB_OUTPUT"
  exit 0
fi
NEXT=$((RETRY_COUNT + 1))
if gh api -X POST "repos/$REPO/actions/runs/$RUN_ID/rerun-failed-jobs" 2>/dev/null; then
  echo "retried=true" >> "$GITHUB_OUTPUT"
  printf -v BODY '%s\n%s%s' \
    "$MARKER" \
    "The CI is failing due to transient infrastructure issues (not related to your code). " \
    "I have restarted the failed jobs automatically ($NEXT/$MAX_RETRIES)."
  gh pr comment "$PR_NUM" --repo "$REPO" --body "$BODY"
else
  echo "::warning::Could not re-run failed jobs (missing actions:write permission?). Skipping auto-retry."
  echo "retried=false" >> "$GITHUB_OUTPUT"
fi
