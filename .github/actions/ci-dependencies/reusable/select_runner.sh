#!/usr/bin/env bash
# Select the runner image of the trusted CI test job for the review.
set -euo pipefail

RUNNER=ubuntu-latest
WORKFLOW=$(mktemp)
if gh api -H "Accept: application/vnd.github.raw" \
  "repos/$REPOSITORY/contents/.github/workflows/ci.yml?ref=$BASE_SHA" >"$WORKFLOW"; then
  CANDIDATE=$(yq '.jobs.test."runs-on" // ""' "$WORKFLOW" 2>/dev/null || true)
  # Unknown Ubuntu labels can route jobs to self-hosted runners. Update this
  # list when GitHub adds or removes supported standard images.
  case "$CANDIDATE" in
    ubuntu-latest|ubuntu-22.04|ubuntu-24.04|ubuntu-26.04) RUNNER=$CANDIDATE ;;
    '') ;;
    *) echo "::warning::Unsupported CI runner for reviews; using $RUNNER" ;;
  esac
fi
rm -f "$WORKFLOW"
echo "runner=$RUNNER" >>"$GITHUB_OUTPUT"
