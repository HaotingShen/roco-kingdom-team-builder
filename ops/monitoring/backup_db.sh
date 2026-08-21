#!/bin/bash
# Nightly logical backup of the on-box Postgres to S3.
# Runs as user `ubuntu` under cron, which has a minimal PATH -> absolute paths only.
# Created 2026-08-21 (Phase 5). Once RDS is deleted this is the ONLY copy of app data.
set -uo pipefail

REGION="ap-southeast-1"
BUCKET="rktb-archive"
CONTAINER="rktb-postgres-1"
DB="roco_kingdom"
USER_="rktb_admin"
MIN_BYTES=5000000          # a real dump is ~15 MB; anything tiny means something broke
LOG="/home/ubuntu/rktb/logs/backup.log"

DATE=$(/usr/bin/date -u +%Y%m%d)
OUT="/tmp/${DB}-${DATE}.dump"
KEY="db/${DB}-${DATE}.dump"

exec >> "$LOG" 2>&1
echo "=== $(/usr/bin/date -u +%FT%TZ) backup start (uid=$(id -un)) ==="

cleanup() { /bin/rm -f "$OUT"; }
trap cleanup EXIT

# 1. dump straight out of the container to the host
if ! /usr/bin/docker exec "$CONTAINER" pg_dump -U "$USER_" -d "$DB" -Fc > "$OUT"; then
  echo "FAIL: pg_dump returned non-zero"; exit 1
fi

# 2. refuse to publish a suspiciously small dump -- a truncated backup that
#    overwrites a good one is worse than a missing backup
SIZE=$(/usr/bin/stat -c%s "$OUT" 2>/dev/null || echo 0)
if [ "$SIZE" -lt "$MIN_BYTES" ]; then
  echo "FAIL: dump is only ${SIZE} bytes (floor ${MIN_BYTES}) - NOT uploading"; exit 1
fi

# 3. verify it is a readable archive before trusting it
if ! /usr/bin/docker run --rm -v /tmp:/t postgres:16 pg_restore --list "/t/$(basename "$OUT")" > /dev/null 2>&1; then
  echo "FAIL: pg_restore --list could not read the dump - NOT uploading"; exit 1
fi

# 4. upload
if ! /usr/bin/aws s3 cp "$OUT" "s3://${BUCKET}/${KEY}" --region "$REGION" --only-show-errors; then
  echo "FAIL: s3 upload failed"; exit 1
fi

# 5. confirm what actually landed in S3 matches what we sent
REMOTE=$(/usr/bin/aws s3api head-object --bucket "$BUCKET" --key "$KEY" --region "$REGION" --query ContentLength --output text 2>/dev/null || echo 0)
if [ "$REMOTE" != "$SIZE" ]; then
  echo "FAIL: size mismatch local=${SIZE} s3=${REMOTE}"; exit 1
fi

echo "OK $(/usr/bin/date -u +%FT%TZ) ${KEY} ${SIZE} bytes"
exit 0
