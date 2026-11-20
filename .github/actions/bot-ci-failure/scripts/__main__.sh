#!/usr/bin/env bash
# Dispatch the CI failure workflow's independent operations.
set -eo pipefail
script_dir=$(dirname "${BASH_SOURCE[0]}")
case "${1:-}" in
  fetch-diff|fetch-logs|retry|post-comment|find-pr) exec bash "$script_dir/$1.sh" ;;
  analyze) exec python "$script_dir/analyze_failure.py" ;;
  *) echo "Unknown CI failure operation: ${1:-}" >&2; exit 2 ;;
esac
