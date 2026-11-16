#!/usr/bin/env bash
set -euo pipefail

DIR=$(dirname "$(realpath "$0")")
sudo useradd --create-home --shell /bin/bash reviewer
sudo install -m 755 "$DIR/sandbox-shell.sh" /usr/local/bin/ai-review-shell
sudo install -d -o reviewer -g reviewer /tmp/ai-review/run
sudo -u reviewer mkdir -p /home/reviewer/.config/pip
printf '[global]\nuser = true\nbreak-system-packages = true\n' |
  sudo -u reviewer tee /home/reviewer/.config/pip/pip.conf >/dev/null
