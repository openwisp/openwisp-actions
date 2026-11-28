#!/usr/bin/env bash
# Keep downloaded APT archives outside the runner image's cleanup directory.
set -euo pipefail

cache="$HOME/.cache/apt-ci/archives"
staging="$HOME/.cache/apt-ci/staging"
if [[ ! "$cache" =~ ^/[A-Za-z0-9_./-]+$ || "$cache" == *..* ]]; then
  echo "Invalid APT cache path" >&2
  exit 1
fi
mkdir -p "$cache/partial" "$staging"
rm -f -- "$cache"/*.deb "$staging"/*.deb
printf 'Dir::Cache::archives "%s/";\nBinary::apt::APT::Keep-Downloaded-Packages "true";\n' "$cache" |
  sudo tee /etc/apt/apt.conf.d/99-openwisp-cache >/dev/null
