#!/usr/bin/env bash
# Install trusted CI dependencies as the unprivileged review user.
set -euo pipefail

RUN=${1:-/tmp/ai-review/run}
REVIEW_HOME=${2:-/home/reviewer}
sudo rsync -a --chown=reviewer:reviewer --exclude=/.git --exclude=/openwisp-actions \
  "$GITHUB_WORKSPACE/" "$RUN/"
# Record base files before installation so synchronization removes files deleted by the PR.
(cd "$GITHUB_WORKSPACE" && find . \( -path ./.git -o -path ./openwisp-actions \
  -o -path ./node_modules \) -prune -o \( -type f -o -type l \) -print0 | LC_ALL=C sort -z) \
  | sudo -u reviewer tee "$REVIEW_HOME/.ai-review-files" >/dev/null
sudo install -d -o reviewer -g reviewer "$REVIEW_HOME/.cache"
if [ -d "$HOME/.cache/pip" ]; then
  sudo cp -a "$HOME/.cache/pip" "$REVIEW_HOME/.cache/"
fi
if [ -n "${YARN_CACHE_DIR:-}" ] && [ -d "$YARN_CACHE_DIR" ]; then
  sudo install -d -o reviewer -g reviewer "$REVIEW_HOME/.cache/yarn"
  sudo cp -a "$YARN_CACHE_DIR" "$REVIEW_HOME/.cache/yarn/"
fi
sudo chown -R reviewer:reviewer "$REVIEW_HOME/.cache"
SYSTEM_DEPS_READY=0
if [ -f "$GITHUB_WORKSPACE/.ci-review-system-deps" ]; then
  # Only trusted base-branch code runs with access to the runner's sudo privileges.
  (cd "$GITHUB_WORKSPACE" && env -i HOME="$HOME" PATH="$PATH" \
    CI_SYSTEM_DEPS_ONLY=1 bash ./install-ci-deps.sh)
  SYSTEM_DEPS_READY=1
fi
cd "$RUN"
sudo -n -H -u reviewer env -i HOME="$REVIEW_HOME" USER=reviewer LOGNAME=reviewer \
  PATH="$PATH" DJANGO_VERSION="${DJANGO_VERSION:-}" CI_QA="${CI_QA:-0}" \
  CI_SYSTEM_DEPS_READY="$SYSTEM_DEPS_READY" \
  YARN_CACHE_FOLDER="$REVIEW_HOME/.cache/yarn" \
  bash ./install-ci-deps.sh
