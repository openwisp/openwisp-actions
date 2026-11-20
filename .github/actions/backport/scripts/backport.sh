#!/usr/bin/env bash
# Cherry-pick a commit onto the caller repository and open a backport PR.
set -e

if [ -z "$SHA" ]; then
  echo "No SHA to cherry-pick, skipping"
  exit 0
fi
if ! git check-ref-format --branch "$BRANCH" > /dev/null 2>&1; then
  echo "::error::Invalid branch name '$BRANCH'"
  exit 1
fi
if ! git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  echo "::error::Target branch '$BRANCH' does not exist"
  exit 1
fi
if ! PR_DATA=$(gh api "repos/$REPO/commits/$SHA/pulls" --jq '.[0] | {number, title}'); then
  echo "::warning::Could not fetch PR data for $SHA, proceeding with commit-based backport branch"
  PR_DATA="null"
fi
PR_NUMBER=$(echo "$PR_DATA" | jq -r '.number // empty')
PR_TITLE=$(echo "$PR_DATA" | jq -r '.title // "Fix from master"')
if [ -z "$PR_NUMBER" ]; then
  BACKPORT_BRANCH="backport/commit-${SHA:0:7}-to-${BRANCH}"
  BODY="Backport of commit $SHA to \`$BRANCH\`."
  PR_TITLE="[backport] $(git log -1 --format=%s "$SHA") (to $BRANCH)"
  COMMIT_BODY=$(git log -1 --format=%b "$SHA")
  if [ -n "$COMMIT_BODY" ]; then
    BODY=$(printf '%s\n\n%s' "$BODY" "$COMMIT_BODY")
  fi
else
  BACKPORT_BRANCH="backport/${PR_NUMBER}-to-${BRANCH}"
  PR_TITLE="[backport] #${PR_NUMBER}: $PR_TITLE (to $BRANCH)"
  BODY="Backport of #$PR_NUMBER to \`$BRANCH\`."
  # The same backport may already be open under a branch with an older timestamp.
  BRANCH_PREFIX="backport/${PR_NUMBER}-to-${BRANCH}-"
  # Stop if the lookup fails. An API error is not evidence that no backport exists.
  # The existing backport may be older than the first page of open PRs.
  OPEN_PRS=$(gh api --method GET --paginate --slurp "repos/$REPO/pulls" \
    -f state=open -f "base=$BRANCH" -F per_page=100)
  # The bot pushes to the caller repository, so fork branches cannot be its backports.
  EXISTING=$(jq -r --arg prefix "$BRANCH_PREFIX" --arg repo "$REPO" '
    first(.[][] | select(.head.repo.full_name == $repo and (.head.ref | startswith($prefix))) | .number)
  ' <<< "$OPEN_PRS")
  if [ -n "$EXISTING" ]; then
    echo "Backport PR #$EXISTING already exists"
    gh pr comment "$PR_NUMBER" --body "Backport to \`$BRANCH\` already exists: #$EXISTING"
    exit 0
  fi
fi
BACKPORT_BRANCH="${BACKPORT_BRANCH}-$(date +%s)"
git checkout -b "$BACKPORT_BRANCH" "origin/$BRANCH"
# An empty cherry-pick also returns nonzero, so inspect Git's state before failing the job.
CHERRY_PICK_STATUS=0
git cherry-pick -x "$SHA" || CHERRY_PICK_STATUS=$?
if [ "$CHERRY_PICK_STATUS" -eq 0 ]; then
  if ! git push origin "$BACKPORT_BRANCH"; then
    echo "::error::Failed to push $BACKPORT_BRANCH"
    exit 1
  fi
  if ! gh pr create \
      --base "$BRANCH" \
      --head "$BACKPORT_BRANCH" \
      --title "$PR_TITLE" \
      --body "$BODY"; then
    echo "::error::Failed to create PR"
    # Remove the branch we just pushed so a failed PR request leaves no remote branch behind.
    git push origin --delete "$BACKPORT_BRANCH" || true
    exit 1
  fi
  {
    echo "## ✅ Backport Successful"
    echo "- **Source**: #$PR_NUMBER"
    echo "- **Target Branch**: $BRANCH"
    echo "- **Backport Branch**: $BACKPORT_BRANCH"
  } >> "$GITHUB_STEP_SUMMARY"
# Git leaves CHERRY_PICK_HEAD on an empty pick, but not when it rejects the commit itself.
elif ! git rev-parse --verify --quiet CHERRY_PICK_HEAD >/dev/null; then
  echo "::error::Could not cherry-pick $SHA onto $BRANCH"
  exit 1
elif git diff --cached --quiet; then
  echo "Commit $SHA appears to already be in $BRANCH (empty cherry-pick)"
  git cherry-pick --abort || true
  exit 0
else
  git cherry-pick --abort || true
  {
    echo "❌ Cherry-pick to \`$BRANCH\` failed due to conflicts. Please backport manually:"
    echo ""
    echo "\`\`\`bash"
    echo "git fetch origin $BRANCH"
    echo "git checkout -b $BACKPORT_BRANCH origin/$BRANCH"
    echo "git cherry-pick -x $SHA"
    echo "# resolve conflicts"
    echo "git cherry-pick --continue"
    echo "git push origin $BACKPORT_BRANCH"
    echo "\`\`\`"
  } > /tmp/backport-comment.md
  [ -n "$PR_NUMBER" ] && gh pr comment "$PR_NUMBER" --body-file /tmp/backport-comment.md
  {
    echo "## ❌ Backport Failed"
    echo "- **Source**: #$PR_NUMBER"
    echo "- **Target Branch**: $BRANCH"
    echo "- **Error**: Cherry-pick failed due to conflicts"
  } >> "$GITHUB_STEP_SUMMARY"
  exit 1
fi
