#!/bin/bash
# check_errors_hourly.sh
# Runs every hour via cron. Alerts via email on new backend errors.
# "New" = not seen in the past 25 hours (deduplication via hash file).

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RKTB_DIR="/home/ubuntu/rktb"
SEEN_FILE="/home/ubuntu/.rktb_seen_errors"
LOG_FILE="$RKTB_DIR/logs/monitor.log"
TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
NOW_EPOCH=$(date +%s)

log() { echo "[$TIMESTAMP] $1" >> "$LOG_FILE"; }

mkdir -p "$RKTB_DIR/logs"

# ── 1. Check container health ────────────────────────────────────────────────
BACKEND_RUNNING=$(/usr/bin/docker compose -f "$RKTB_DIR/docker-compose.prod.yml" \
    ps --services --filter "status=running" 2>/dev/null | grep -c "backend" || echo 0)

if [ "$BACKEND_RUNNING" -eq 0 ]; then
    log "CRITICAL: backend container is not running — sending alert"

    RESEND_API_KEY=$(/usr/bin/aws ssm get-parameter \
        --name /rktb/prod/SMTP_PASSWORD --with-decryption \
        --query Parameter.Value --output text --region ap-southeast-1 2>/dev/null)

    if [ -n "$RESEND_API_KEY" ]; then
        export RESEND_API_KEY TIMESTAMP
        python3 << 'PYEOF'
import urllib.request, json, os
api_key   = os.environ["RESEND_API_KEY"]
timestamp = os.environ["TIMESTAMP"]
payload = json.dumps({
    "from":    "noreply@rkteambuilder.com",
    "to":      ["shenhaoting@gmail.com"],
    "subject": "[RKTB CRITICAL] Backend container is DOWN",
    "text":    f"Detected at: {timestamp}\n\nThe rktb-backend-1 container is not running.\n\nTo restart:\nssh ubuntu@13.228.63.192 \"cd /home/ubuntu/rktb && docker compose -f docker-compose.prod.yml up -d backend\""
}).encode()
req = urllib.request.Request("https://api.resend.com/emails", data=payload,
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
             "User-Agent": "curl/7.81.0"})
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"Container-down alert sent — HTTP {resp.status}")
except urllib.error.HTTPError as e:
    print(f"Failed to send alert: HTTP {e.code} — {e.read().decode(errors='replace')}")
except Exception as e:
    print(f"Failed to send alert: {e}")
PYEOF
    fi
    exit 0
fi

# ── 2. Fetch last 65 min of logs (overlap avoids edge-of-hour gaps) ──────────
TEMP_ALL=$(mktemp)
/usr/bin/docker compose -f "$RKTB_DIR/docker-compose.prod.yml" \
    logs --since 65m backend 2>&1 > "$TEMP_ALL"

# Extract real errors only:
#   "- ERROR -"  → our app logger (backend.main, backend.cache, etc.)
#   "| ERROR:"   → uvicorn unhandled exceptions / startup failures
#   "Traceback"  → Python tracebacks
TEMP_ERRORS=$(mktemp)
grep -E "(- ERROR -|\| ERROR:?\s|Traceback \(most recent call last\))" "$TEMP_ALL" > "$TEMP_ERRORS"
rm -f "$TEMP_ALL"

if [ ! -s "$TEMP_ERRORS" ]; then
    rm -f "$TEMP_ERRORS"
    exit 0
fi

# ── 3. Deduplicate against seen hashes ───────────────────────────────────────
touch "$SEEN_FILE"

# Purge hashes older than 25 hours
CUTOFF=$((NOW_EPOCH - 90000))
awk -v cutoff="$CUTOFF" 'NF>=2 && $2+0 > cutoff' "$SEEN_FILE" > "${SEEN_FILE}.tmp" 2>/dev/null \
    && mv "${SEEN_FILE}.tmp" "$SEEN_FILE"

TEMP_NEW=$(mktemp)
while IFS= read -r line; do
    [ -z "$line" ] && continue
    # Strip variable parts before hashing so same error = same hash
    SIG=$(echo "$line" \
        | sed 's/[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\} [0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}[.,][0-9]*/TS/g' \
        | sed 's/[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}/IP/g' \
        | sed 's/\bID=[0-9][0-9]*/ID=N/g' \
        | sed 's/user [0-9][0-9]*/user N/g' \
        | sed 's/line [0-9][0-9]*/line N/g' \
        | cut -c1-150)
    HASH=$(echo "$SIG" | md5sum | cut -d' ' -f1)
    if ! grep -q "^$HASH " "$SEEN_FILE" 2>/dev/null; then
        echo "$HASH $NOW_EPOCH" >> "$SEEN_FILE"
        echo "$line" >> "$TEMP_NEW"
    fi
done < "$TEMP_ERRORS"
rm -f "$TEMP_ERRORS"

if [ ! -s "$TEMP_NEW" ]; then
    rm -f "$TEMP_NEW"
    exit 0
fi

ERROR_COUNT=$(wc -l < "$TEMP_NEW")
log "Found $ERROR_COUNT new error(s) — sending alert"

# ── 4. Fetch Resend key and email ────────────────────────────────────────────
RESEND_API_KEY=$(/usr/bin/aws ssm get-parameter \
    --name /rktb/prod/SMTP_PASSWORD --with-decryption \
    --query Parameter.Value --output text --region ap-southeast-1 2>/dev/null)

if [ -z "$RESEND_API_KEY" ]; then
    log "ERROR: Could not fetch Resend API key from SSM"
    rm -f "$TEMP_NEW"
    exit 1
fi

export RESEND_API_KEY TIMESTAMP ERROR_COUNT TEMP_NEW

python3 << 'PYEOF'
import urllib.request, json, os, html as html_mod

api_key     = os.environ["RESEND_API_KEY"]
timestamp   = os.environ["TIMESTAMP"]
count       = os.environ["ERROR_COUNT"].strip()
errors_file = os.environ["TEMP_NEW"]

with open(errors_file, "r", errors="replace") as f:
    errors_raw = f.read().strip()

errors_html = html_mod.escape(errors_raw)

html_body = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;font-size:13px;color:#333;max-width:900px;">
  <h2 style="color:#cc0000;">&#9888; RKTB Backend Alert &mdash; {count} new error(s)</h2>
  <p><strong>Detected at:</strong> {timestamp}</p>
  <hr style="border:none;border-top:1px solid #ddd;"/>
  <pre style="background:#fff8f8;padding:14px;border-left:4px solid #cc0000;
              overflow-x:auto;font-size:11px;line-height:1.6;
              white-space:pre-wrap;word-break:break-all;">{errors_html}</pre>
  <hr style="border:none;border-top:1px solid #ddd;"/>
  <p style="color:#888;font-size:11px;">
    View recent logs:<br/>
    <code>ssh ubuntu@13.228.63.192 "cd /home/ubuntu/rktb &amp;&amp; docker compose -f docker-compose.prod.yml logs --since 2h backend 2&gt;&amp;1 | tail -300"</code>
  </p>
</body></html>"""

payload = json.dumps({
    "from":    "noreply@rkteambuilder.com",
    "to":      ["shenhaoting@gmail.com"],
    "subject": f"[RKTB Alert] {count} new backend error(s) detected",
    "html":    html_body,
    "text":    f"Detected at: {timestamp}\n\nNew error(s):\n\n{errors_raw}"
}).encode()

req = urllib.request.Request("https://api.resend.com/emails", data=payload,
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
             "User-Agent": "curl/7.81.0"})
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"Alert sent — HTTP {resp.status}")
except urllib.error.HTTPError as e:
    print(f"Failed to send alert: HTTP {e.code} — {e.read().decode(errors='replace')}")
except Exception as e:
    print(f"Failed to send alert: {e}")
PYEOF

rm -f "$TEMP_NEW"
