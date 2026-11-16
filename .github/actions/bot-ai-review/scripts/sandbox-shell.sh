#!/usr/bin/env bash
exec sudo -n -H -u reviewer -- /bin/bash -c '
rsync -a /tmp/ai-review/pr/ /tmp/ai-review/run/
case "$PWD/" in
  /tmp/ai-review/pr/*) cd "/tmp/ai-review/run${PWD#/tmp/ai-review/pr}" || exit 1 ;;
esac
exec /bin/bash "$@"' ai-review-shell "$@"
