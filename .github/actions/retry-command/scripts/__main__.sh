#!/usr/bin/env bash
# Run the retry loop for the composite action.
set -eo pipefail
script_dir=$(dirname "${BASH_SOURCE[0]}")
exec bash -eo pipefail "$script_dir/retry.sh"
