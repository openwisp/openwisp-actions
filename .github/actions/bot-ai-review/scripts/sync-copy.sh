#!/usr/bin/env bash
set -euo pipefail

export LC_ALL=C
SRC=$1
DST=$2
LIST=$3
exec 9>"$LIST.lock"
flock 9
NEW=$(mktemp "$LIST.XXXXXX")
(cd "$SRC" && find . \( -type f -o -type l \) -print0 | sort -z) >"$NEW"
if [ -f "$LIST" ]; then
  comm -z -23 "$LIST" "$NEW" | (cd "$DST" && xargs -0 -r rm -f --)
fi
rsync -a "$SRC/" "$DST/"
mv "$NEW" "$LIST"
