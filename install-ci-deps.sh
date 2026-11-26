#!/usr/bin/env bash
# Install the Python dependencies shared by CI and AI review experiments.
set -euo pipefail

COMMAND='python -m pip install -r requirements-test.txt' \
  MAX_ATTEMPTS=3 DELAY_SECONDS=5 bash .github/actions/retry-command/retry.sh
