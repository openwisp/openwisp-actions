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
mkdir -p "$HOME/.cache/ci-deps"
SYSTEM_DEPS_READY=0
if [ -f "$GITHUB_WORKSPACE/.ci-review-system-deps" ]; then
  # Run only the system phase from trusted base code before the reviewer sees PR files.
  # The reviewer phase must skip system setup because it has no sudo privileges.
  (cd "$GITHUB_WORKSPACE" && env -i HOME="$HOME" PATH="$PATH" \
    CI_DEPS_CACHE="$HOME/.cache/ci-deps" CI_SYSTEM_DEPS_ONLY=1 bash ./install-ci-deps.sh)
  SYSTEM_DEPS_READY=1
fi
if [ -d "$HOME/.cache/ci-deps" ]; then
  sudo cp -a "$HOME/.cache/ci-deps" "$REVIEW_HOME/.cache/"
  sudo chown -R reviewer:reviewer "$REVIEW_HOME/.cache/ci-deps"
fi
cd "$RUN"
sudo -n -H -u reviewer env -i HOME="$REVIEW_HOME" USER=reviewer LOGNAME=reviewer \
  PATH="$PATH" DJANGO_VERSION="${DJANGO_VERSION:-}" CI_QA="${CI_QA:-0}" \
  CI_SYSTEM_DEPS_READY="$SYSTEM_DEPS_READY" \
  CI_DEPS_CACHE="$REVIEW_HOME/.cache/ci-deps" \
  YARN_CACHE_FOLDER="$REVIEW_HOME/.cache/yarn" \
  bash ./install-ci-deps.sh
