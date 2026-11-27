#!/usr/bin/env bash
# Publish review findings and dismiss superseded reviews of the same stage.
set -euo pipefail

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
if [ "${CI_AWARE:-false}" = true ]; then
  # Identify this exact publication when returning its URL to the waiting request.
  REVIEW_MARKER="<!-- ai-review-run ${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT:-1} -->"
  BODY+=$'\n\n'"$REVIEW_MARKER"
fi
COMMENTS="$RUNNER_TEMP/comments.json"
jq '.comments' "$FINDINGS" >"$COMMENTS"
CURRENT_SHA=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER" --jq '.head.sha')
CURRENT_STATE=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER" --jq '.state')
CURRENT_BASE=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER" --jq '.base.ref')
if [ "$CURRENT_SHA" != "$HEAD_SHA" ]; then
  echo "::error::The pull request head changed during the review; request another review"
  exit 1
fi
if [ "$CURRENT_STATE" != open ]; then
  echo "::error::The pull request closed during the review"
  exit 1
fi
if [ "$CURRENT_BASE" != "$BASE_REF" ]; then
  echo "::error::The pull request base changed during the review; request another review"
  exit 1
fi
post_review() {
  jq -n --arg body "$BODY" --arg event "$EVENT" --arg commit "$HEAD_SHA" \
    --slurpfile comments "$COMMENTS" '{
    body: $body,
    commit_id: $commit,
    event: {comment: "COMMENT", approve: "APPROVE", "request-changes": "REQUEST_CHANGES"}[$event],
    comments: [$comments[0][] | {path: .file, line: .line, side: "RIGHT", body: .body}]
  } | if (.comments | length) == 0 then del(.comments) else . end' |
    gh api -X POST "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews" --input - --include
}
ERROR="$RUNNER_TEMP/review-error.txt"
RESPONSE="$RUNNER_TEMP/review-response.txt"
if ! post_review >"$RESPONSE" 2>"$ERROR"; then
  # Include the response body: gh may omit detailed validation errors from stderr.
  IFS= read -r STATUS <"$RESPONSE" || true
  # A 422 rejects the whole review. Other failures can be ambiguous, so do not retry them.
  if [ "$(jq 'length' "$COMMENTS")" -gt 0 ] && \
    [[ "$STATUS" =~ ^HTTP/[0-9.]+[[:space:]]422[[:space:]] ]] && \
    grep -Fq 'Diff entry ' "$RESPONSE" && grep -Fq 'diff is too large' "$RESPONSE"; then
    BODY+=$'\n\n**Inline findings (GitHub could not display the diff):**\n\n'
    BODY+=$(jq -r '.[] | "- `\(.file):\(.line)`\n\n\(.body)\n"' "$COMMENTS")
    jq -n '[]' >"$COMMENTS"
    post_review >/dev/null
  else
    cat "$ERROR" >&2
    exit 1
  fi
fi
if [ "${CI_AWARE:-false}" = true ] && [ -n "${RECORD_ID:-}" ]; then
  # Match the marker and the app's bot account, not an unrelated review of the same commit.
  if BOT_ID=$(gh api "repos/$REPOSITORY/issues/comments/$RECORD_ID" --jq '.user.id') && \
    REVIEW_URL=$(gh api --paginate "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews" | \
      jq -rs --arg marker "$REVIEW_MARKER" --arg bot "$BOT_ID" '
        [.[][] | select((.user.id | tostring) == $bot and ((.body // "") | contains($marker)))]
        | if length == 1 then .[0].html_url else empty end') && \
    [[ "$REVIEW_URL" == https://* && "$REVIEW_URL" != *$'\n'* ]]; then
    printf 'review_url=%s\n' "$REVIEW_URL" >> "$GITHUB_OUTPUT"
  else
    echo '::warning::Published review link is unavailable.'
  fi
fi
case "$VERDICT" in
  "Review not completed" | Inconclusive | "Maintainer decision needed") exit 0 ;;
esac

# Do not use the app's dismissal permission on another reviewer's change requests.
REVIEW_IDS="$RUNNER_TEMP/earlier-reviews.txt"
NOTICE=""
if gh api --paginate "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews" |
  jq -rs --arg prefix "AI $STAGE of " '
    [.[][] | select(.user.login == "openwisp-companion[bot]" and (.body | startswith($prefix)))]
    | sort_by(.id) | .[:-1][]
    | select(.state == "CHANGES_REQUESTED") | .id' >"$REVIEW_IDS"; then
  while read -r REVIEW_ID; do
    if ! gh api -X PUT "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews/$REVIEW_ID/dismissals" \
      -f message="Superseded by a newer AI $STAGE." -f event=DISMISS --silent; then
      echo "::warning::Published the review, but could not dismiss earlier review $REVIEW_ID"
      NOTICE+=" Earlier review $REVIEW_ID could not be dismissed."
    fi
  done <"$REVIEW_IDS"
else
  echo "::warning::Published the review, but could not list earlier reviews for dismissal"
  NOTICE=" Earlier reviews could not be checked for dismissal."
fi
if [ -n "$NOTICE" ]; then
  NOTICE="The AI $STAGE was published, but superseded change requests may still be active.$NOTICE"
  NOTICE+=" Please check earlier Companion reviews and dismiss superseded requests if appropriate."
  if ! jq -n --arg body "$NOTICE" --arg commit "$HEAD_SHA" \
    '{body: $body, commit_id: $commit, event: "COMMENT"}' |
    gh api -X POST "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews" --input - --silent; then
    echo "::warning::Could not post the dismissal warning to the pull request"
  fi
fi
