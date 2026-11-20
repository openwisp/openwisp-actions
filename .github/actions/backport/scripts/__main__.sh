#!/usr/bin/env bash
# Dispatch the backport workflow's separate operations.
set -e

script_dir=$(dirname "${BASH_SOURCE[0]}")
case "${1:-}" in
  parse|backport) exec bash "$script_dir/$1.sh" ;;
  *) echo "Usage: $0 {parse|backport}" >&2; exit 2 ;;
esac
