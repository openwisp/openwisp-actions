#!/usr/bin/env bash
set -euo pipefail

DIR=$(dirname "$(realpath "$0")")
if [ -z "$MODEL" ]; then
  echo "::error::Set OPENCODE_PROVIDER and the AI_REVIEW*_MODEL variable for $STAGE"
  exit 1
fi
EVENTS="$RUNNER_TEMP/events.jsonl"
OUTPUT="$RUNNER_TEMP/output.txt"
export OPENCODE_CONFIG="$DIR/../opencode.json"
export OPENCODE_DISABLE_PROJECT_CONFIG=1
export OPENCODE_DISABLE_EXTERNAL_SKILLS=1
export OPENCODE_ENABLE_EXA=1
export XDG_DATA_HOME="$RUNNER_TEMP/opencode-data"

if (cd "$PR_DIR" && opencode debug skill --pure) \
  | jq -e '.[] | select(.location != "<built-in>")' >/dev/null; then
  echo "::error::Repository skills were loaded"
  exit 1
fi

opencode models "${MODEL%%/*}" --refresh || true
chmod a-w "$DATA_DIR"/*
FILES=(--file "$DATA_DIR/pr.diff")
if [ "$STAGE" = review ] && [ -s "$DATA_DIR/guidance.md" ]; then
  FILES+=(--file "$DATA_DIR/guidance.md")
fi
if [ "$STAGE" = review ]; then
  FILES+=(--file "$DATA_DIR/threat-model.rst")
fi
FILES+=(--file "$DATA_DIR/context.json" --file "$DATA_DIR/history.json")
case "$STAGE" in
  review) STEP=1 ;;
  security-review) STEP=2 ;;
  final-review) STEP=3 ;;
esac
PROMPT=$(cat "$DIR/../prompts/$STEP-$STAGE.md" "$RUNNER_TEMP/shared-guidance/guidance.md" \
  "$DIR/../prompts/verification.md")
STATUS=0
timeout --kill-after=30s 25m opencode run "$PROMPT" --pure --format json \
  --model "$MODEL" --dir "$PR_DIR" "${FILES[@]}" </dev/null >"$EVENTS" || STATUS=$?
if [ "$STATUS" -eq 124 ] || [ "$STATUS" -eq 137 ]; then
  echo "::warning::The review hit the 25-minute limit"
fi

AUTH="$XDG_DATA_HOME/opencode/auth.json"
if [ -f "$AUTH" ]; then
  TOKEN=$(jq -r '.[].refresh' "$AUTH")
  rm -f "$AUTH"
  if grep -qF -- "$TOKEN" "$EVENTS"; then
    echo "::error::The model output contains a credential"
    exit 1
  fi
fi

if [ "$STATUS" -ne 0 ]; then
  echo "::error::The model run did not complete (exit status: $STATUS)"
  exit 1
fi

STOP=$(openssl rand -hex 16)
echo "::stop-commands::$STOP"
jq -r 'select(.type == "error") | "Error: \(.error.data.message // .error.name)"' "$EVENTS" || true
jq -r 'select(.type == "tool_use") | .part | "Tool: \(.tool) (\(.state.status)) \(.state.input.command // .state.input.url // "")"' "$EVENTS" || true
jq -r 'select(.type == "step_finish") | .part
  | "Step: \(.reason), output tokens: \(.tokens.output), reasoning tokens: \(.tokens.reasoning)"' \
  "$EVENTS" || true
echo "::$STOP::"
jq -rs '[.[] | select(.type == "text") | .part.text] | last // ""' "$EVENTS" >"$OUTPUT"
if ! [ -s "$OUTPUT" ] || ! grep -q '[^[:space:]]' "$OUTPUT"; then
  REASON=$(jq -rs '[.[] | select(.type == "step_finish") | .part.reason] | last // "none"' "$EVENTS")
  echo "::error::The model ended without an answer (finish reason: $REASON)"
  exit 1
fi

python3 "$DIR/extract_findings.py" "$OUTPUT" "$DATA_DIR/pr.diff" "$STAGE" \
  >"$RUNNER_TEMP/findings.json"
if [ -s "$RUNNER_TEMP/shared-guidance/notes.md" ]; then
  jq --rawfile notes "$RUNNER_TEMP/shared-guidance/notes.md" \
    '.summary += "\n" + ($notes | rtrimstr("\n"))' "$RUNNER_TEMP/findings.json" \
    >"$RUNNER_TEMP/findings.tmp"
  mv "$RUNNER_TEMP/findings.tmp" "$RUNNER_TEMP/findings.json"
fi
if jq -e '.verdict == "Review not completed"' "$RUNNER_TEMP/findings.json" >/dev/null; then
  echo "::group::Model answer"
  echo "::stop-commands::$STOP"
  cat "$OUTPUT"
  echo
  echo "::$STOP::"
  echo "::endgroup::"
fi
echo "::stop-commands::$STOP"
cat "$RUNNER_TEMP/findings.json"
echo "::$STOP::"
