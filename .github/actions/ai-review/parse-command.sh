#!/usr/bin/env bash
set -euo pipefail

REVIEW_MODEL=github-copilot/gpt-6.1-terra
SECURITY_MODEL=github-copilot/gpt-6-astra
COMMAND=$(printf '%s' "$BODY" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
PATTERN='^(/[a-z-]+)([[:space:]]+(copilot|opencode)/([a-z0-9.-]+))?$'
if ! [[ "$COMMAND" =~ $PATTERN ]]; then
  echo "Not a review command"
  exit 0
fi
case "${BASH_REMATCH[1]}" in
  /review) STAGE=review MODEL=$REVIEW_MODEL ;;
  /security-review) STAGE=security-review MODEL=$SECURITY_MODEL ;;
  /final-review) STAGE=final-review MODEL=$REVIEW_MODEL ;;
  *)
    echo "Not a review command"
    exit 0
    ;;
esac
case "${BASH_REMATCH[3]}" in
  copilot) MODEL="github-copilot/${BASH_REMATCH[4]}" ;;
  opencode) MODEL="opencode/${BASH_REMATCH[4]}" ;;
esac
echo "stage=$STAGE" >>"$GITHUB_OUTPUT"
echo "model=$MODEL" >>"$GITHUB_OUTPUT"
