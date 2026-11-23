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
cd "$RUN"
sudo -n -H -u reviewer env -i HOME="$REVIEW_HOME" USER=reviewer LOGNAME=reviewer \
  PATH="$PATH" DJANGO_VERSION="${DJANGO_VERSION:-}" CI_QA="${CI_QA:-0}" \
  YARN_CACHE_FOLDER="$REVIEW_HOME/.cache/yarn" \
  bash ./install-ci-deps.sh
