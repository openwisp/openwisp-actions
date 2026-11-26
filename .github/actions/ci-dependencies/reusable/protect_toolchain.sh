#!/usr/bin/env bash
# Prevent the reviewer from changing files later used with credentials.
set -euo pipefail

check_parents() {
  local parent=$1 encoded
  while [ "$parent" != / ]; do
    if sudo -n -u reviewer test -w "$parent"; then
      case "$parent" in
        /tmp|/home|/usr)
          encoded=$(printf '%s' "$parent" | base64 -w0)
          echo "::error::Unsafe writable parent (base64): $encoded" >&2
          return 1
          ;;
      esac
      sudo chmod go-w -- "$parent"
      if sudo -n -u reviewer test -w "$parent"; then
        encoded=$(printf '%s' "$parent" | base64 -w0)
        echo "::error::Reviewer-writable protected directory (base64): $encoded" >&2
        return 1
      fi
    fi
    parent=$(dirname "$parent")
  done
}

protected=("${RUNNER_TOOL_CACHE:?}" "${RUNNER_TEMP:?}" "${GITHUB_WORKSPACE:?}")
for path in "$(dirname "$RUNNER_TEMP")/_actions" "$HOME/runners" "$HOME/.config" "$HOME/.local"; do
  [ ! -d "$path" ] || protected+=("$path")
done
for path in "${protected[@]}"; do
  path=$(realpath -e "$path")
  case "$path" in /|/tmp|/home|/opt|/usr) echo "::error::Unsafe protection root" >&2; exit 1 ;; esac
  sudo chmod -R go-w -- "$path"
  if [ -n "$(sudo find "$path" -user reviewer -print -quit)" ]; then
    echo "::error::Reviewer owns a protected file" >&2
    exit 1
  fi
  if sudo -n -u reviewer test -x "$path"; then
    writable=$(sudo -n -u reviewer find "$path" \( ! -type l -writable -print -quit \) -o \
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
tool_cache=$(realpath -e "$RUNNER_TOOL_CACHE")
safe_path=()
for path in "${path_entries[@]}"; do
  case "$path" in /*) ;; *) echo "::error::Unsafe PATH entry" >&2; exit 1 ;; esac
  case "$path" in *$'\n'*|*$'\r'*) echo "::error::Invalid PATH entry" >&2; exit 1 ;; esac
  [ -d "$path" ] || continue
  resolved=$(realpath -e "$path")
  parent=$resolved
  unsafe=false
  while [ "$parent" != / ]; do
    if sudo -n -u reviewer test -w "$parent"; then unsafe=true; break; fi
    parent=$(dirname "$parent")
  done
  [ "$unsafe" = false ] || continue
  if ! sudo -n -u reviewer test -x "$path"; then
    safe_path+=("$path")
    continue
  fi
  # A searchable but unreadable directory cannot be audited reliably.
  if ! sudo -n -u reviewer test -r "$path"; then continue; fi
  writable=$(sudo -n -u reviewer find -L "$path" -maxdepth 1 -type f -writable -print -quit)
  [ -z "$writable" ] || continue
  case "$(realpath -e "$path")" in
    "$tool_cache"/*)
      # Only selected runtimes matter; other cached SDKs may link outside the cache.
      runtime=$(dirname "$(realpath -e "$path")")
      if [ -n "$(sudo find -L "$runtime" -user reviewer -print -quit)" ] ||
        [ -n "$(sudo -n -u reviewer find -L "$runtime" -writable -print -quit -o \
          \( -type d ! -readable -prune \))" ]; then
        echo "::error::Reviewer-writable runtime file" >&2
        exit 1
      fi
      ;;
  esac
  safe_path+=("$path")
done
if [ "${#safe_path[@]}" -eq 0 ]; then
  echo "::error::No safe PATH entries" >&2
  exit 1
fi
printf '%s\n' "$(IFS=:; printf '%s' "${safe_path[*]}")"
