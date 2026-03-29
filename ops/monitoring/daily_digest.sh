#!/bin/bash
# daily_digest.sh
# Wrapper for daily_digest.py. Fetches SSM secrets, then runs the Python digest.
# Cron: 30 21 * * *  (21:30 UTC = 30 min after the daily backend restart)

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RKTB_DIR="/home/ubuntu/rktb"
LOG_FILE="$RKTB_DIR/logs/monitor.log"
TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

mkdir -p "$RKTB_DIR/logs"
echo "[$TIMESTAMP] Starting daily digest" >> "$LOG_FILE"

export RKTB_DIR

export RESEND_API_KEY=$(/usr/bin/aws ssm get-parameter \
    --name /rktb/prod/SMTP_PASSWORD --with-decryption \
    --query Parameter.Value --output text --region ap-southeast-1 2>/dev/null)

if [ -z "$RESEND_API_KEY" ]; then
    echo "[$TIMESTAMP] ERROR: Could not fetch Resend API key from SSM" >> "$LOG_FILE"
    exit 1
fi

python3 /home/ubuntu/daily_digest.py >> "$LOG_FILE" 2>&1
echo "[$TIMESTAMP] Daily digest complete (exit $?)" >> "$LOG_FILE"
