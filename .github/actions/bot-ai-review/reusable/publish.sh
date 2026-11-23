#!/usr/bin/env bash
# Publish review findings and dismiss superseded reviews of the same stage.
set -euo pipefail

git fetch --no-tags origin "refs/pull/$PR_NUMBER/head"
git checkout -B "ai-review-$PR_NUMBER" "$HEAD_SHA"

EVENT=$(jq -er '.event' "$FINDINGS")
VERDICT=$(jq -er '.verdict' "$FINDINGS")
TITLE=$(jq -r '.title // empty' "$FINDINGS")
SUMMARY=$(jq -er '.summary' "$FINDINGS")
BODY="AI $STAGE of $HEAD_SHA provided by \`${MODEL%%/*}\` / \`${MODEL#*/}\`

**Verdict: $VERDICT**

"
if [ "${CI_AWARE:-false}" != true ]; then
  BODY+="
CI was not checked or awaited. Maintainers can enable CI-aware reviews:
https://github.com/openwisp/openwisp-actions/issues/39

"
fi
case "${CI_STANDARD_STATUS:-unknown}" in
  missing)
    BODY+="Missing CI entry points on the base branch: $CI_STANDARD_MISSING.
See https://github.com/openwisp/openwisp-actions/issues/39.

" ;;
  unknown)
    BODY+="CI entry points could not be checked on the base branch.

" ;;
esac
if [ -n "$TITLE" ]; then
  BODY+="$TITLE

"
fi
BODY+=$SUMMARY
COMMENTS="$RUNNER_TEMP/comments.json"
jq '.comments' "$FINDINGS" >"$COMMENTS"
CURRENT_SHA=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER" --jq '.head.sha')
CURRENT_STATE=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER" --jq '.state')
CURRENT_BASE=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER" --jq '.base.ref')
if [ "$CURRENT_SHA" != "$HEAD_SHA" ] || [ "$CURRENT_STATE" != open ] || \
  [ "$CURRENT_BASE" != "$BASE_REF" ]; then
  echo "::error::The pull request changed or closed during the review, request it again"
  exit 1
fi
if [ "$(jq 'length' "$COMMENTS")" -eq 0 ]; then
  jq -n --arg body "$BODY" --arg event "$EVENT" --arg commit "$HEAD_SHA" '{
    body: $body,
    commit_id: $commit,
    event: {comment: "COMMENT", approve: "APPROVE", "request-changes": "REQUEST_CHANGES"}[$event]
  }' | gh api -X POST "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews" --input - --silent
else
  crit comment --json --file "$COMMENTS"
  crit push "$PR_NUMBER" --event "$EVENT" --message "$BODY"
fi
case "$VERDICT" in
  "Review not completed" | Inconclusive | "Maintainer decision needed") exit 0 ;;
esac

# Keep the newest review for this stage. Dismiss only the earlier bot change requests.
gh api --paginate "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews" |
  jq -rs --arg prefix "AI $STAGE of " '
    [.[][] | select(.user.type == "Bot" and (.body | startswith($prefix)))]
    | sort_by(.id) | .[:-1][]
    | select(.state == "CHANGES_REQUESTED") | .id' |
  while read -r REVIEW_ID; do
    gh api -X PUT "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews/$REVIEW_ID/dismissals" \
      -f message="Superseded by a newer AI $STAGE." -f event=DISMISS --silent
  done
