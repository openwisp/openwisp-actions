#!/usr/bin/env bash
set -euo pipefail

git fetch --no-tags origin "refs/pull/$PR_NUMBER/head"
git checkout -B "ai-review-$PR_NUMBER" "$HEAD_SHA"

EVENT=$(jq -er '.event' "$FINDINGS")
VERDICT=$(jq -er '.verdict' "$FINDINGS")
TITLE=$(jq -r '.title // empty' "$FINDINGS")
SUMMARY=$(jq -er '.summary' "$FINDINGS")
BODY="AI $STAGE of $HEAD_SHA using \`$MODEL\`

**Verdict: $VERDICT**

"
if [ -n "$TITLE" ]; then
  BODY+="$TITLE

"
fi
BODY+=$SUMMARY
COMMENTS="$RUNNER_TEMP/comments.json"
jq '.comments' "$FINDINGS" >"$COMMENTS"
if [ "$(jq 'length' "$COMMENTS")" -eq 0 ]; then
  echo "::error::The pull request has no lines the review can be attached to"
  exit 1
fi
CURRENT_SHA=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER" --jq '.head.sha')
if [ "$CURRENT_SHA" != "$HEAD_SHA" ]; then
  echo "::error::The pull request changed during the review, request it again"
  exit 1
fi
crit comment --json --file "$COMMENTS"
crit push "$PR_NUMBER" --event "$EVENT" --message "$BODY"

gh api --paginate "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews" |
  jq -rs --arg prefix "AI $STAGE of " '
    [.[][] | select(.user.type == "Bot" and (.body | startswith($prefix)))]
    | sort_by(.id) | .[:-1][]
    | select(.state == "CHANGES_REQUESTED") | .id' |
  while read -r REVIEW_ID; do
    gh api -X PUT "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews/$REVIEW_ID/dismissals" \
      -f message="Superseded by a newer AI $STAGE." -f event=DISMISS --silent
  done
