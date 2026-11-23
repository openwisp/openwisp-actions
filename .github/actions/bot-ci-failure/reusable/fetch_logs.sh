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
if [ -n "${MAX_LOG_BYTES:-}" ]; then
  if ! [[ "$MAX_LOG_BYTES" =~ ^[0-9]+$ ]] || [ "$MAX_LOG_BYTES" -eq 0 ]; then
    echo "MAX_LOG_BYTES must be a positive integer." >&2
    exit 1
  fi
  JOB_COUNT=$(wc -w <<<"$JOB_IDS")
  JOB_LIMIT=$((MAX_LOG_BYTES / JOB_COUNT))
  if [ "$JOB_LIMIT" -lt 32 ]; then
    echo "MAX_LOG_BYTES is too small for the failed jobs." >&2
    exit 1
  fi
fi
: > failed_logs.txt
FOUND_ERROR=false
for JOB_ID in $JOB_IDS; do
  echo "Processing job $JOB_ID"
  if ! gh api --allow-escape-sequences "repos/$REPO/actions/jobs/$JOB_ID/logs" > job_logs.txt; then
    if [ -n "${MAX_LOG_BYTES:-}" ]; then
      printf 'Job %s logs unavailable.\n' "$JOB_ID" | head -c "$JOB_LIMIT" >> failed_logs.txt
    else
      echo "Could not fetch logs for job $JOB_ID; skipping." >> failed_logs.txt
    fi
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
  } > job_excerpt.txt
  if grep -q "##\[error\]" job_excerpt.txt; then
    FOUND_ERROR=true
  fi
  if [ -n "${MAX_LOG_BYTES:-}" ] && [ "$(wc -c < job_excerpt.txt)" -gt "$JOB_LIMIT" ]; then
    # Give each failed job a share of the limit so a long job cannot hide another job's error.
    MARKER=$'\n[truncated]\n'
    KEEP_BYTES=$((JOB_LIMIT - ${#MARKER}))
    START_BYTES=$((KEEP_BYTES / 3))
    END_BYTES=$((KEEP_BYTES - START_BYTES))
    {
      head -c "$START_BYTES" job_excerpt.txt
      printf '%s' "$MARKER"
      tail -c "$END_BYTES" job_excerpt.txt
    } >> failed_logs.txt
  else
    cat job_excerpt.txt >> failed_logs.txt
  fi
done
if [ ! -s failed_logs.txt ] || [ "$FOUND_ERROR" != true ]; then
  echo "Failed jobs found but logs unavailable." > failed_logs.txt
fi
