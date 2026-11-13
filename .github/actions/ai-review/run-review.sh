#!/usr/bin/env bash
set -euo pipefail

DIR=$(dirname "$(realpath "$0")")
EVENTS="$RUNNER_TEMP/events.jsonl"
OUTPUT="$RUNNER_TEMP/output.txt"
export OPENCODE_CONFIG="$DIR/opencode.json"
export XDG_DATA_HOME="$RUNNER_TEMP/opencode-data"

opencode models "${MODEL%%/*}" --refresh || true
FILES=(--file "$RUNNER_TEMP/pr.diff")
if [ -f "$RUNNER_TEMP/history.json" ]; then
  FILES+=(--file "$RUNNER_TEMP/history.json")
fi
opencode run "$(cat "$DIR/$STAGE.md")" --pure --format json --model "$MODEL" \
  --dir "$RUNNER_TEMP/pr" "${FILES[@]}" </dev/null >"$EVENTS" || true

AUTH="$XDG_DATA_HOME/opencode/auth.json"
if [ -f "$AUTH" ]; then
  TOKEN=$(jq -r '.[].refresh' "$AUTH")
  rm -f "$AUTH"
  if grep -qF -- "$TOKEN" "$EVENTS"; then
    echo "::error::The model output contains a credential"
    exit 1
  fi
fi

jq -r 'select(.type == "error") | "Error: \(.error.data.message // .error.name)"' "$EVENTS" || true
jq -r 'select(.type == "tool_use") | .part | "Tool: \(.tool) (\(.state.status))"' "$EVENTS" || true
jq -r 'select(.type == "step_finish") | .part
  | "Step: \(.reason), output tokens: \(.tokens.output), reasoning tokens: \(.tokens.reasoning)"' \
  "$EVENTS" || true
jq -rs '[.[] | select(.type == "text") | .part.text] | last // ""' "$EVENTS" >"$OUTPUT"
if ! [ -s "$OUTPUT" ] || ! grep -q '[^[:space:]]' "$OUTPUT"; then
  REASON=$(jq -rs '[.[] | select(.type == "step_finish") | .part.reason] | last // "none"' "$EVENTS")
  echo "::error::The model ended without an answer (finish reason: $REASON)"
  exit 1
fi

python3 "$DIR/extract_findings.py" "$OUTPUT" "$RUNNER_TEMP/pr.diff" "$STAGE" \
  >"$RUNNER_TEMP/findings.json"
cat "$RUNNER_TEMP/findings.json"
