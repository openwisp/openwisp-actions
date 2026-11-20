#!/usr/bin/env bash
# Require an eligible current approval for the exact pull request head.
set -euo pipefail
PR=$(gh api "repos/$REPOSITORY/pulls/$PR_NUMBER")
HEAD_SHA=$(jq -er '.head.sha' <<< "$PR")
BASE_SHA=$(jq -er '.base.sha' <<< "$PR")
if [ "$HEAD_SHA" != "$EXPECTED_HEAD_SHA" ]; then
  echo "::error::The pull request head changed while verifying approval"
  exit 1
fi
REVIEWS=$(gh api --paginate --slurp "repos/$REPOSITORY/pulls/$PR_NUMBER/reviews?per_page=100")
if ! jq -e --arg head_sha "$HEAD_SHA" '
  [.[][] | select(.user.id != null and .state != "COMMENTED" and .state != "PENDING")]
  | group_by(.user.id)
  | map(max_by([.submitted_at // "", .id]))
  | any(.[];
    .state == "APPROVED" and
    .commit_id == $head_sha and
    (.author_association == "OWNER" or
     .author_association == "MEMBER" or
     .author_association == "COLLABORATOR")
  )
' <<< "$REVIEWS" > /dev/null; then
  echo "::error::The pull request has no current eligible approval"
  exit 1
fi
echo "head_sha=$HEAD_SHA" >> "$GITHUB_OUTPUT"
echo "base_sha=$BASE_SHA" >> "$GITHUB_OUTPUT"
