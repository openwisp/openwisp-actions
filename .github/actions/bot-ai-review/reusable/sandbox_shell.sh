#!/usr/bin/env bash
# Run review commands as the sandbox user in a synchronized working copy.
# Pass command arguments through "$@" so the wrapper does not interpolate them into its shell code.
# Preserve the CI-selected runtimes when sudo resets PATH for the sandbox user.
exec sudo -n -H -u reviewer -- /usr/bin/env -i HOME=/home/reviewer USER=reviewer LOGNAME=reviewer \
  XDG_CONFIG_HOME=/home/reviewer/.config XDG_CACHE_HOME=/home/reviewer/.cache \
  XDG_DATA_HOME=/home/reviewer/.local/share \
  "PATH=/home/reviewer/.local/bin:${AI_REVIEW_SANDBOX_PATH:-$PATH}" \
  CI_DEPS_CACHE=/home/reviewer/.cache/ci-deps \
  "SE_CHROME=${SE_CHROME:-}" "SE_CHROMEDRIVER=${SE_CHROMEDRIVER:-}" \
  "CHROME_BIN=${SE_CHROME:-}" "GECKO_BIN=${GECKO_BIN:-}" SELENIUM_HEADLESS=1 /bin/bash -c '
/usr/local/bin/ai-review-sync /tmp/ai-review/pr /tmp/ai-review/run "$HOME/.ai-review-files" || exit 1
if [ -x /tmp/ai-review/run/.venv/bin/python ]; then
  export VIRTUAL_ENV=/tmp/ai-review/run/.venv
  export PATH="$VIRTUAL_ENV/bin:$PATH"
fi
case "$PWD/" in
  /tmp/ai-review/pr/*) cd "/tmp/ai-review/run${PWD#/tmp/ai-review/pr}" || exit 1 ;;
esac
exec /bin/bash "$@"' ai-review-shell "$@"
