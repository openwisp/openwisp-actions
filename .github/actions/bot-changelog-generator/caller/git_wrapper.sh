#!/usr/bin/env bash
# Supply API-fetched PR data to the generator without checking out PR code.
set -euo pipefail
case "${1:-}" in
  diff) cat "$RUNNER_TEMP/changelog-generator.diff" ;;
  log) cat "$RUNNER_TEMP/changelog-generator.commits" ;;
  *) exec /usr/bin/git "$@" ;;
esac
