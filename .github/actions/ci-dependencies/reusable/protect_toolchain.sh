#!/usr/bin/env bash
# Prevent the reviewer from changing files later used with credentials.
set -euo pipefail

check_parents() {
  local parent=$1
  while [ "$parent" != / ]; do
    if sudo -n -u reviewer test -w "$parent"; then
      echo "::error::Reviewer-writable protected directory" >&2
      return 1
    fi
    parent=$(dirname "$parent")
  done
}

for path in "${RUNNER_TOOL_CACHE:?}" "${RUNNER_TEMP:?}" "${GITHUB_WORKSPACE:?}"; do
  path=$(realpath -e "$path")
  case "$path" in /|/tmp|/home|/opt|/usr) echo "::error::Unsafe protection root" >&2; exit 1 ;; esac
  sudo chmod -R go-w -- "$path"
  if [ -n "$(sudo find -L "$path" -user reviewer -print -quit)" ]; then
    echo "::error::Reviewer owns a protected file" >&2
    exit 1
  fi
  if sudo -n -u reviewer test -x "$path"; then
    writable=$(sudo -n -u reviewer find -L "$path" -writable -print -quit -o \
      \( -type d ! -readable -prune \))
    if [ -n "$writable" ]; then
      # Paths are encoded so file names cannot create workflow commands in logs.
      encoded=$(printf '%s' "$writable" | base64 -w0)
      echo "::error::Reviewer-writable protected file (base64): $encoded" >&2
      exit 1
    fi
  fi
  check_parents "$(dirname "$path")"
done

IFS=: read -r -a path_entries <<<"$PATH"
for path in "${path_entries[@]}"; do
  case "$path" in /*) ;; *) echo "::error::Unsafe PATH entry" >&2; exit 1 ;; esac
  [ -d "$path" ] || continue
  check_parents "$(realpath -e "$path")"
  if [ -n "$(sudo -n -u reviewer find -L "$path" -maxdepth 1 -writable -print -quit)" ]; then
    echo "::error::Reviewer-writable PATH entry" >&2
    exit 1
  fi
done
