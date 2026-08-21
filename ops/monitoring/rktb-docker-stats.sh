#!/bin/bash
# RKTB container resource logger.
# Replaces a fragile "@reboot nohup ... &" crontab entry that died silently on
# 2026-07-03 and left the daily digest's memory trend empty for seven weeks.
# systemd restarts this if it ever exits; the crontab version could not.
# Format is intentionally identical to the original so daily_digest.py keeps parsing it.
LOG=/home/ubuntu/rktb/docker_stats.log
while true; do
  echo "$(/usr/bin/date -u +'%Y-%m-%d %H:%M:%S') $(/usr/bin/docker stats --no-stream --format '{{.Name}} CPU:{{.CPUPerc}} MEM:{{.MemUsage}}')" >> "$LOG"
  sleep 5
done
