#!/usr/bin/env bash
set -euo pipefail

AUTH_DIR="$RUNNER_TEMP/opencode-data/opencode"
mkdir -p "$AUTH_DIR"
jq -n --arg token "$OPENCODE_AUTH" \
  '{"github-copilot": {type: "oauth", refresh: $token, access: $token, expires: 0}}' \
  >"$AUTH_DIR/auth.json"
chmod 600 "$AUTH_DIR/auth.json"
