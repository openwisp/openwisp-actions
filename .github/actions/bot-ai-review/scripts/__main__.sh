#!/usr/bin/env bash
# Dispatch separate AI review workflow steps without crossing their trust boundaries.
set -euo pipefail
script_dir=$(dirname "${BASH_SOURCE[0]}")
case "${1:-}" in
  configure-credentials|fetch-history|fetch-pull-request|fetch-shared-guidance|fetch-threat-model|\
  install-crit|parse-command|prepare-sandbox|publish|read-pull-request|run-review|update-reaction)
    exec bash "$script_dir/$1.sh" ;;
  *) echo "Unknown AI review operation: ${1:-}" >&2; exit 2 ;;
esac
