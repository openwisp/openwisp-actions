#!/usr/bin/env bash
# Start or remove review services from the trusted default-branch Compose file.
set -euo pipefail

case "${1:?Expected start or stop}" in
  start)
    config=$(mktemp "${RUNNER_TEMP:?}/review-ci.XXXXXXXX")
    trap 'rm -f -- "$config"' EXIT
    if ! git -C "$GITHUB_WORKSPACE" show "${DEFAULT_SHA:?}:.github/workflows/ci.yml" \
      >"$config" 2>/dev/null; then
      exit 0
    fi
    services=$(yq -r '.jobs.test.env.AI_REVIEW_SERVICES // ""' "$config")
    case "$services" in
      '') exit 0 ;;
      redis|influxdb|redis,influxdb|influxdb,redis) ;;
      *) echo '::error::Unsupported AI_REVIEW_SERVICES' >&2; exit 1 ;;
    esac
    [[ "${GITHUB_RUN_ID:?}" =~ ^[0-9]+$ && "${GITHUB_RUN_ATTEMPT:?}" =~ ^[0-9]+$ ]]
    directory=$(mktemp -d "$RUNNER_TEMP/ai-review-services.XXXXXXXX")
    project="ai-review-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
    git -C "$GITHUB_WORKSPACE" worktree add --quiet --detach "$directory" "$DEFAULT_SHA"
    printf 'directory=%s\nproject=%s\n' "$directory" "$project" >>"$GITHUB_OUTPUT"
    IFS=, read -r -a names <<<"$services"
    # Compose reads only the trusted checkout and cannot inherit workflow tokens.
    (cd "$directory" && env -i HOME="$HOME" PATH="$PATH" CI=true \
      docker compose -p "$project" up -d --no-build --no-deps "${names[@]}")
    ;;
  stop)
    directory=${2:?Missing service worktree}
    project=${3:?Missing Compose project}
    [[ "$directory" == "$RUNNER_TEMP"/ai-review-services.* ]]
    [[ "$project" =~ ^ai-review-[0-9]+-[0-9]+$ ]]
    status=0
    (cd "$directory" && env -i HOME="$HOME" PATH="$PATH" CI=true \
      docker compose -p "$project" down --volumes --remove-orphans) || status=$?
    git -C "$GITHUB_WORKSPACE" worktree remove --force "$directory" || status=$?
    exit "$status"
    ;;
  *) echo 'Expected start or stop' >&2; exit 1 ;;
esac
