#!/usr/bin/env bash
# Dispatch separate changelog runner validation and preparation steps.
set -eo pipefail
script_dir=$(dirname "${BASH_SOURCE[0]}")
case "${1:-}" in
  check-title|read-metadata|verify-association|verify-approval|prepare-diff)
    exec bash "$script_dir/$1.sh" ;;
  generate) exec python "$script_dir/generate_changelog.py" ;;
  *) echo "Unknown changelog runner operation: ${1:-}" >&2; exit 2 ;;
esac
