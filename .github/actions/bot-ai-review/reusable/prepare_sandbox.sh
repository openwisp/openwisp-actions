#!/usr/bin/env bash
# Prepare the separate user and shell used to run review commands.
set -euo pipefail

DIR=$(dirname "$(realpath "$0")")
sudo useradd --create-home --shell /bin/bash reviewer
sudo install -m 755 "$DIR/sandbox_shell.sh" /usr/local/bin/ai-review-shell
sudo install -m 755 "$DIR/sync_copy.sh" /usr/local/bin/ai-review-sync
sudo install -d -o reviewer -g reviewer /tmp/ai-review/run
sudo -u reviewer mkdir -p /home/reviewer/.config/pip
# Pip falls back to the user site when needed, without breaking virtualenvs.
printf '[global]\nbreak-system-packages = true\n' |
  sudo -u reviewer tee /home/reviewer/.config/pip/pip.conf >/dev/null
