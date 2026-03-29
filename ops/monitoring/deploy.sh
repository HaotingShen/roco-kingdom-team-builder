#!/bin/bash
# deploy.sh — run from local machine to deploy monitoring to EC2
# Usage: bash ops/monitoring/deploy.sh

set -e
EC2="ubuntu@13.228.63.192"
KEY="$HOME/.ssh/rktb-key.pem"
DIR="ops/monitoring"

echo "==> Uploading scripts..."
scp -i "$KEY" "$DIR/check_errors_hourly.sh" "$DIR/daily_digest.sh" "$DIR/daily_digest.py" \
    "$EC2:/home/ubuntu/"

echo "==> Uploading logrotate config..."
scp -i "$KEY" "$DIR/logrotate.conf" "$EC2:/tmp/rktb-logrotate.conf"

echo "==> Configuring EC2..."
ssh -i "$KEY" "$EC2" << 'REMOTE'
set -e

# Permissions
chmod +x /home/ubuntu/check_errors_hourly.sh /home/ubuntu/daily_digest.sh
chmod +x /home/ubuntu/daily_digest.py

# Logs directory
mkdir -p /home/ubuntu/rktb/logs

# Install logrotate config
sudo cp /tmp/rktb-logrotate.conf /etc/logrotate.d/rktb
sudo logrotate --debug /etc/logrotate.d/rktb   # dry-run to verify syntax

# Add cron jobs (idempotent — skip if already present)
CRON=$(crontab -l 2>/dev/null || true)

if ! echo "$CRON" | grep -q "check_errors_hourly"; then
    (echo "$CRON"; echo "0 * * * * /home/ubuntu/check_errors_hourly.sh >> /home/ubuntu/rktb/logs/monitor.log 2>&1") | crontab -
    echo "Added hourly error check cron"
else
    echo "Hourly error check cron already present — skipped"
fi

if ! echo "$CRON" | grep -q "daily_digest"; then
    (crontab -l 2>/dev/null; echo "30 21 * * * /home/ubuntu/daily_digest.sh") | crontab -
    echo "Added daily digest cron"
else
    echo "Daily digest cron already present — skipped"
fi

echo ""
echo "==> Current crontab:"
crontab -l
REMOTE

echo ""
echo "==> Deploy complete."
echo "    Run a test: ssh -i $KEY $EC2 '/home/ubuntu/daily_digest.sh'"
