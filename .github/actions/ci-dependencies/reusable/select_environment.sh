#!/usr/bin/env bash
# Select the review environment from the trusted CI matrix.
set -euo pipefail

DIR=$(dirname "$(realpath "$0")")
JOB=$(yq -o=json '.jobs.test' "$CI_ROOT/.github/workflows/ci.yml")
MATRIX=$(jq '.strategy.matrix // null' <<<"$JOB")
PYTHON_VERSION=
DJANGO_VERSION=
NODE_VERSION=
if [ "$MATRIX" = null ]; then
  if [ -n "${REVIEW_MATRIX_OVERRIDE:-}" ]; then
    echo "::error::A matrix override requires a CI matrix" >&2
    exit 1
  fi
else
  ARGS=()
  if [ -n "${REVIEW_MATRIX_OVERRIDE:-}" ]; then
    ARGS+=("$REVIEW_MATRIX_OVERRIDE")
  fi
  ROW=$(python3 "$DIR/select_matrix.py" "${ARGS[@]}" <<<"$MATRIX")
  PYTHON_VERSION=$(jq -r '.["python-version"] // ""' <<<"$ROW")
  DJANGO_VERSION=$(jq -r '.["django-version"] // ""' <<<"$ROW")
  NODE_VERSION=$(jq -r '.["node-version"] // ""' <<<"$ROW")
fi
if [ -z "$PYTHON_VERSION" ]; then
  PYTHON_VERSION=$(jq -r '[.steps[]? | select((.uses // "") | startswith("actions/setup-python@")) |
    .with["python-version"] // ""] | first // ""' <<<"$JOB")
fi
if [ -z "$NODE_VERSION" ]; then
  NODE_VERSION=$(jq -r '[.steps[]? | select((.uses // "") | startswith("actions/setup-node@")) |
    .with["node-version"] // ""] | first // ""' <<<"$JOB")
fi
NODE_VERSION_FILE=$(jq -r '[.steps[]? | select((.uses // "") | startswith("actions/setup-node@")) |
  .with["node-version-file"] // ""] | first // ""' <<<"$JOB")
if [ -z "$NODE_VERSION" ] && [ -z "$NODE_VERSION_FILE" ] && [ -f "$CI_ROOT/.nvmrc" ]; then
  NODE_VERSION_FILE=.nvmrc
fi
if [ -z "$PYTHON_VERSION" ] && [ -z "$NODE_VERSION_FILE" ] && [ -z "$NODE_VERSION" ]; then
  echo "::error::$CI_ROOT/.github/workflows/ci.yml: unsupported review runtime" >&2
  exit 1
fi
BROWSERS=$(jq -r '.env.AI_REVIEW_BROWSERS // ""' <<<"$JOB")
if [ -z "$BROWSERS" ]; then
  # Preserve the existing pilot's browser setup without assuming all Node projects need Chrome.
  BROWSERS=$(jq -r 'if any(.steps[]?; (.uses // "") | startswith("browser-actions/setup-chrome@"))
    then "chrome" else "none" end' <<<"$JOB")
fi
CHROME=false
FIREFOX=false
case "$BROWSERS" in
  none) ;;
  chrome) CHROME=true ;;
  firefox) FIREFOX=true ;;
  chrome,firefox|firefox,chrome) CHROME=true; FIREFOX=true ;;
  *) echo "::error::Unsupported AI_REVIEW_BROWSERS: $BROWSERS" >&2; exit 1 ;;
esac
{
  echo "python_version=$PYTHON_VERSION"
  echo "django_version=$DJANGO_VERSION"
  echo "node_version_file=$NODE_VERSION_FILE"
  echo "node_version=$NODE_VERSION"
  echo "chrome=$CHROME"
  echo "firefox=$FIREFOX"
} >> "$GITHUB_OUTPUT"
