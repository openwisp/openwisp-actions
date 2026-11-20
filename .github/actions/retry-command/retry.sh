#!/usr/bin/env bash
# Retry the caller's shell command in the same shell on each attempt.
set -eo pipefail

readonly COMMAND DELAY_SECONDS MAX_ATTEMPTS
attempts=0
until [ "$attempts" -ge "$MAX_ATTEMPTS" ]; do
  echo "Attempt $((attempts+1)) of $MAX_ATTEMPTS..."
  # The caller supplies a shell command, which can include pipes or redirects.
  eval "$COMMAND" && break
  attempts=$((attempts+1))
  if [ "$attempts" -lt "$MAX_ATTEMPTS" ]; then
    echo "Command failed. Waiting ${DELAY_SECONDS}s before retry..."
    sleep "$DELAY_SECONDS"
  else
    echo "Command failed after $attempts attempts."
    exit 1
  fi
done
