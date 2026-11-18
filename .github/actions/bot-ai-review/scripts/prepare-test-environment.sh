#!/usr/bin/env bash
set -euo pipefail

read -ra PACKAGES <<<"$APT_PACKAGES"
read -ra SERVICES <<<"$COMPOSE_SERVICES"
read -ra PIP_ARGS <<<"$PIP_INSTALL"
for NAME in "${PACKAGES[@]}" "${SERVICES[@]}"; do
  if ! [[ "$NAME" =~ ^[a-z0-9][a-z0-9.+_-]*$ ]]; then
    echo "::error::Invalid package or service name"
    exit 1
  fi
done

if [ "${#PACKAGES[@]}" -gt 0 ]; then
  sudo apt-get update -qq
  sudo apt-get install -qq -y --no-install-recommends "${PACKAGES[@]}"
fi
if [ "${#SERVICES[@]}" -gt 0 ]; then
  docker compose -f "$GITHUB_WORKSPACE/docker-compose.yml" up -d --wait "${SERVICES[@]}"
fi
if [ "${#PIP_ARGS[@]}" -gt 0 ]; then
  sudo -n -H -u reviewer -- bash -c 'cd "$1" && shift && pip install "$@"' \
    _ "$PR_DIR" "${PIP_ARGS[@]}"
fi
