#!/usr/bin/env bash
# Collect failed job log sections between GitHub group and error markers.
set -eo pipefail
echo "Getting failed jobs for run $RUN_ID..."
if ! JOB_IDS=$(gh api --paginate "repos/$REPO/actions/runs/$RUN_ID/jobs" \
  -q '.jobs[] | select(.conclusion=="failure") | .id'); then
  echo "Could not fetch failed jobs for run $RUN_ID." > failed_logs.txt
  exit 0
fi
if [ -z "$JOB_IDS" ]; then
  echo "No failed jobs found." > failed_logs.txt
  exit 0
fi
: > failed_logs.txt
for JOB_ID in $JOB_IDS; do
  echo "Processing job $JOB_ID"
  if ! gh api --allow-escape-sequences "repos/$REPO/actions/jobs/$JOB_ID/logs" > job_logs.txt; then
    echo "Could not fetch logs for job $JOB_ID; skipping." >> failed_logs.txt
    continue
  fi
  {
    echo "===== JOB $JOB_ID ====="
    awk '
    /##\[group\]/ {
        buffer = $0 "\n"
        next
    }
    {
        buffer = buffer $0 "\n"
        if (/##\[error\]/) {
            printf "%s\n", buffer
            buffer = ""
        }
    }
    ' job_logs.txt
    echo ""
  } >> failed_logs.txt
done
if [ ! -s failed_logs.txt ] || ! grep -q "##\[error\]" failed_logs.txt; then
  echo "Failed jobs found but logs unavailable." > failed_logs.txt
fi
