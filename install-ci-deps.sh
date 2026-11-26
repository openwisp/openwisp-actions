#!/usr/bin/env bash
# Install the dependencies shared by CI and AI review experiments.
set -euo pipefail

COMMAND='python -m pip install -r requirements-test.txt' \
  MAX_ATTEMPTS=3 DELAY_SECONDS=5 bash .github/actions/retry-command/retry.sh

# Review commands already put the reviewer's ~/.local/bin on PATH.
npm install --global --ignore-scripts --prefix "$HOME/.local" prettier@3.9.4
if [ -n "${GITHUB_PATH:-}" ]; then
  printf '%s\n' "$HOME/.local/bin" >> "$GITHUB_PATH"
fi
