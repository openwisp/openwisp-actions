#!/usr/bin/env bash
# Dispatch version branch operations without changing the caller's working directory.
set -e
script_dir=$(dirname "${BASH_SOURCE[0]}")
case "${1:-}" in
  version) exec python "$script_dir/version.py" ;;
  replicate) exec bash "$script_dir/replicate.sh" ;;
  *) echo "Usage: $0 {version|replicate}" >&2; exit 2 ;;
esac
