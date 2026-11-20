#!/usr/bin/env bash
# Accept only a single small regular PR number file from the untrusted artifact.
set -eo pipefail
PR_NUMBER_FILE="$ARTIFACT_DIR/pr_number"
if [ ! -d "$ARTIFACT_DIR" ] || [ -L "$ARTIFACT_DIR" ]; then
  echo "::error::Invalid metadata artifact directory"
  exit 1
fi
# List hidden entries too, and preserve filenames containing whitespace when counting entries.
mapfile -d '' ARTIFACT_FILES < <(find "$ARTIFACT_DIR" -mindepth 1 -maxdepth 1 -print0)
if [ "${#ARTIFACT_FILES[@]}" -ne 1 ] || [ "${ARTIFACT_FILES[0]}" != "$PR_NUMBER_FILE" ] || \
  [ -L "$PR_NUMBER_FILE" ] || [ ! -f "$PR_NUMBER_FILE" ]; then
  echo "::error::Metadata artifact must contain only a regular pr_number file"
  exit 1
fi
FILE_SIZE=$(stat -c %s "$PR_NUMBER_FILE")
if [ "$FILE_SIZE" -gt 16 ]; then
  echo "::error::Metadata artifact is too large"
  exit 1
fi
PR_NUMBER=$(< "$PR_NUMBER_FILE")
if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "::error::Invalid PR number: $PR_NUMBER"
  exit 1
fi
echo "pr_number=$PR_NUMBER" >> "$GITHUB_OUTPUT"
