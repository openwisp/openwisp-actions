#!/usr/bin/env bash
# Select the review stage and model from a pull request comment.
set -euo pipefail

COMMAND=$(printf '%s' "$BODY" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
case "$COMMAND" in
  /review) STAGE=review NAME=${GENERAL_MODEL:-} ;;
  /security-review) STAGE=security-review NAME=${SECURITY_MODEL:-} ;;
  /final-review) STAGE=final-review NAME=${FINAL_MODEL:-} ;;
  *)
    echo "Not a review command"
    exit 0
    ;;
esac
echo "stage=$STAGE" >>"$GITHUB_OUTPUT"
if [ -n "${PROVIDER:-}" ] && [ -n "$NAME" ]; then
  echo "model=$PROVIDER/$NAME" >>"$GITHUB_OUTPUT"
fi
