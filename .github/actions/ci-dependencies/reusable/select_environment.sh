#!/usr/bin/env bash
# Select the review environment from the trusted CI matrix.
set -euo pipefail

DIR=$(dirname "$(realpath "$0")")
JOB=$(yq -o=json '.jobs.test' "$CI_ROOT/.github/workflows/ci.yml")
MATRIX=$(jq '.strategy.matrix // null' <<<"$JOB")
if [ "$MATRIX" = null ]; then
  if [ -n "${REVIEW_MATRIX_OVERRIDE:-}" ]; then
    echo "::error::A matrix override requires a CI matrix" >&2
    exit 1
  fi
  PYTHON_VERSION=$(jq -r '[.steps[] | select((.uses // "") | startswith("actions/setup-python@")) |
    .with["python-version"] // ""] | first // ""' <<<"$JOB")
  DJANGO_VERSION=
else
  ARGS=()
  if [ -n "${REVIEW_MATRIX_OVERRIDE:-}" ]; then
    ARGS+=("$REVIEW_MATRIX_OVERRIDE")
  fi
  ROW=$(python3 "$DIR/select_matrix.py" "${ARGS[@]}" <<<"$MATRIX")
  PYTHON_VERSION=$(jq -r '.["python-version"] // ""' <<<"$ROW")
  DJANGO_VERSION=$(jq -r '.["django-version"] // ""' <<<"$ROW")
fi
NODE_VERSION_FILE=
if [ -z "$PYTHON_VERSION" ] && [ -f "$CI_ROOT/.nvmrc" ]; then
  NODE_VERSION_FILE=.nvmrc
fi
if [ -z "$PYTHON_VERSION" ] && [ -z "$NODE_VERSION_FILE" ]; then
  echo "::error::$CI_ROOT/.github/workflows/ci.yml: unsupported review runtime" >&2
  exit 1
fi
{
  echo "python_version=$PYTHON_VERSION"
  echo "django_version=$DJANGO_VERSION"
  echo "node_version_file=$NODE_VERSION_FILE"
} >> "$GITHUB_OUTPUT"
