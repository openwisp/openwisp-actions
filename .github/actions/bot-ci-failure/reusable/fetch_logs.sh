#!/usr/bin/env bash
# Collect failed job log sections between GitHub group and error markers.
set -eo pipefail
echo "Getting failed jobs for run $RUN_ID..."
JOBS_ENDPOINT="repos/$REPO/actions/runs/$RUN_ID"
# The reviewer needs logs from the attempt it selected, even if CI is retried.
if [ -n "${ATTEMPT:-}" ]; then
  JOBS_ENDPOINT+="/attempts/$ATTEMPT"
fi
if ! JOB_IDS=$(gh api --paginate "$JOBS_ENDPOINT/jobs" \
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
    # Start a fresh buffer at each group header and keep it only if an error follows.
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
# Keep the existing failure-bot output unless a caller requests a size limit.
if [ -n "${MAX_LOG_BYTES:-}" ] && [ "$(wc -c < failed_logs.txt)" -gt "$MAX_LOG_BYTES" ]; then
  # Keep both the job header and the final error, which often follows a long test log.
  START_BYTES=$((MAX_LOG_BYTES / 2))
  END_BYTES=$((MAX_LOG_BYTES - START_BYTES))
  head -c "$START_BYTES" failed_logs.txt > failed_logs.truncated
  printf '\n[Failed-job excerpts truncated.]\n' >> failed_logs.truncated
  tail -c "$END_BYTES" failed_logs.txt >> failed_logs.truncated
  mv failed_logs.truncated failed_logs.txt
fi
