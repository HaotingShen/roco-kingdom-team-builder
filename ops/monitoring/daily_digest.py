#!/usr/bin/env python3
"""
daily_digest.py — RKTB Daily Health Digest
Called by daily_digest.sh which sets: RESEND_API_KEY, RKTB_DIR
Runs at 21:30 UTC (30 min after daily backend restart).
"""

import os
import re
import json
import time
import subprocess
import urllib.request
import urllib.error
import html as html_mod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter

RKTB_DIR   = Path(os.environ.get("RKTB_DIR", "/home/ubuntu/rktb"))
API_KEY    = os.environ.get("RESEND_API_KEY", "")
NOW        = datetime.now(timezone.utc)
TODAY      = NOW.strftime("%Y-%m-%d")


# ── Helpers ──────────────────────────────────────────────────────────────────

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.stdout.strip()
    except Exception as e:
        return f"[error: {e}]"

def parse_mem_mb(s):
    """'237MiB / 2.80GiB' → float MiB used, or None"""
    m = re.match(r'([\d.]+)\s*(GiB|MiB|GB|MB|kB|KB|B)', s.strip())
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2)
    if u in ('GiB', 'GB'): return v * 1024
    if u in ('kB', 'KB'):  return v / 1024
    if u == 'B':            return v / 1048576
    return v

def fmt_mb(mb):
    if mb is None: return "N/A"
    return f"{mb/1024:.2f} GiB" if mb >= 1024 else f"{mb:.0f} MiB"

def h(text):
    """HTML-escape a value for safe inline use."""
    return html_mod.escape(str(text))


# ── 1. Container logs — last 24h via CloudWatch ──────────────────────────────

print("Fetching 24h logs from CloudWatch...")

NOW_MS   = int(time.time() * 1000)
START_MS = NOW_MS - 86400000  # 24h in milliseconds

def cw_fetch(filter_pattern, max_events=2000):
    """
    Query CloudWatch with a filter pattern. Returns list of message strings.
    Uses CloudWatch-side filtering so only matching events are transferred.
    Paginates until max_events reached or no more results.
    """
    messages       = []
    next_token_arg = ""
    while len(messages) < max_events:
        result = subprocess.run(
            f"aws logs filter-log-events"
            f" --log-group-name /rktb/backend"
            f" --log-stream-names backend"
            f" --start-time {START_MS}"
            f" --end-time {NOW_MS}"
            f" --filter-pattern {filter_pattern}"
            f" --region ap-southeast-1"
            f" --output json"
            f" {next_token_arg}",
            shell=True, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"CloudWatch error ({filter_pattern}): {result.stderr[:100]}")
            break
        data       = json.loads(result.stdout)
        messages  += [e["message"] for e in data.get("events", [])]
        token      = data.get("nextToken")
        if not token:
            break
        next_token_arg = f"--next-token '{token}'"
    return messages

# Targeted queries — CloudWatch filters before transferring data
print("  errors...")
error_lines   = cw_fetch('"ERROR"')
print("  warnings...")
warning_lines = cw_fetch('"WARNING"')
print("  analyses...")
analysis_lines   = cw_fetch('"Team analysis took"')
cachehit_lines   = cw_fetch('"All cache keys found"')
partial_lines    = cw_fetch('"Partial analysis success"')
login_lines      = cw_fetch('"Failed login attempt"')
lockout_lines    = cw_fetch('"Account locked"')
guestclean_lines = cw_fetch('"Guest cleanup"')
promptclean_lines= cw_fetch('"Prompt log cleanup"')

# Keep a combined `lines` list only for backward-compat with norm() below
lines = error_lines + warning_lines

error_count = len(error_lines)
warning_count = len(warning_lines)

def norm(line, pattern):
    """Extract message after pattern, strip numbers for grouping."""
    m = re.search(pattern + r'(.+)', line)
    msg = m.group(1) if m else line
    return re.sub(r'\b\d+\b', 'N', msg).strip()[:100]

top_errors   = Counter(norm(l, r'- ERROR - ')   for l in error_lines  ).most_common(5)
top_warnings = Counter(norm(l, r'- WARNING - ')  for l in warning_lines).most_common(5)

# Analysis activity (from targeted CloudWatch queries)
analyses_total   = len(analysis_lines)
cache_hits       = len(cachehit_lines)
partial_failures = len(partial_lines)

# Auth activity
failed_logins   = len(login_lines)
locked_accounts = len(lockout_lines)

# Background job results
def last_count(matched_lines):
    if not matched_lines: return '0'
    m = re.search(r'deleted (\d+)', matched_lines[-1])
    return m.group(1) if m else '?'

guest_cleanup  = last_count(guestclean_lines)
prompt_cleanup = last_count(promptclean_lines)


# ── 2. Current container stats ───────────────────────────────────────────────

print("Fetching current container stats...")
stats_out = run('docker stats --no-stream --format "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}"')
containers = {}
for line in stats_out.splitlines():
    parts = line.split('|')
    if len(parts) == 3:
        name, cpu, mem = [p.strip() for p in parts]
        mem_mb = parse_mem_mb(mem.split('/')[0]) if '/' in mem else None
        containers[name] = {'cpu': cpu, 'mem_raw': mem, 'mem_mb': mem_mb}


# ── 3. Backend memory trend from docker_stats.log ────────────────────────────

print("Parsing memory trend from docker_stats.log...")
stats_log   = Path("/home/ubuntu/rktb/docker_stats.log")
mem_samples = []

if stats_log.exists():
    # ~55 000 lines ≈ 24h at 5 s intervals × 3 containers
    tail = run(f"tail -55000 {stats_log}")
    for line in tail.splitlines():
        if 'backend' not in line.lower():
            continue
        m = re.search(r'MEM:([\d.]+\s*(?:GiB|MiB|MB|GB|kB))\s*/', line)
        if m:
            mb = parse_mem_mb(m.group(1))
            if mb is not None:
                mem_samples.append(mb)

mem_min    = min(mem_samples)  if mem_samples else None
mem_max    = max(mem_samples)  if mem_samples else None
mem_avg    = sum(mem_samples) / len(mem_samples) if mem_samples else None
mem_growth = (mem_max - mem_min) if (mem_min and mem_max) else None


# ── 4. Daily restart status ───────────────────────────────────────────────────

print("Checking restart log...")
restart_log = RKTB_DIR / "logs" / "restart.log"
restart_ok, restart_note = False, "Log not found"
if restart_log.exists():
    # Check if file was modified today (restart runs at 21:00 UTC)
    mtime = restart_log.stat().st_mtime
    modified_today = (NOW.timestamp() - mtime) < 3600  # within last hour
    last_line = run(f"tail -1 {restart_log}").strip()
    if not last_line:
        restart_note = "Log exists but empty"
    elif modified_today and last_line == "rktb-backend-1":
        restart_ok   = True
        restart_note = "Success"
    elif modified_today:
        restart_ok   = False
        restart_note = f"Failed — {last_line}"
    else:
        restart_note = "Not yet run today (or log not updated)"


# ── 5. Prompt logs & disk usage ──────────────────────────────────────────────

print("Checking prompt logs...")
prompt_dir     = RKTB_DIR / "logs" / "prompts" / TODAY
today_prompts  = len(list(prompt_dir.glob("*.txt"))) if prompt_dir.exists() else 0
logs_disk      = run(f"du -sh {RKTB_DIR / 'logs'} 2>/dev/null | cut -f1") or "N/A"
stats_log_size = run(f"du -sh {stats_log} 2>/dev/null | cut -f1") if stats_log.exists() else "N/A"


# ── 6. Build HTML email ───────────────────────────────────────────────────────

print("Building digest email...")

def table(rows):
    cells = "".join(
        f'<tr>'
        f'<td style="padding:5px 14px 5px 0;color:#666;white-space:nowrap;">{h(k)}</td>'
        f'<td style="padding:5px 14px 5px 0;font-weight:600;">{h(v)}</td>'
        f'</tr>'
        for k, v in rows
    )
    return f'<table style="border-collapse:collapse;font-size:13px;">{cells}</table>'

def section_html(title, content, color="#2c7bb6"):
    return (
        f'<h3 style="color:{color};border-bottom:2px solid {color};'
        f'padding-bottom:4px;margin:24px 0 8px;">{title}</h3>'
        + content
    )

def ul(items, empty_msg="None"):
    if not items:
        return f'<p style="color:#2a9d2a;">{empty_msg}</p>'
    lis = "".join(
        f'<li style="font-family:monospace;font-size:11px;margin-bottom:3px;">'
        f'{h(msg[:100])} <span style="color:#888;">×{cnt}</span></li>'
        for msg, cnt in items
    )
    return f'<ul style="margin:4px 0;padding-left:20px;">{lis}</ul>'

err_color   = "#cc0000" if error_count > 0 else "#2a9d2a"
err_icon    = "⚠" if error_count > 0 else "✓"
rst_icon    = "✓" if restart_ok else "⚠"
timestamp_s = NOW.strftime('%Y-%m-%d %H:%M:%S UTC')

# Container rows
container_rows = [
    (name, f"{s['mem_raw']}  ·  CPU {s['cpu']}")
    for name, s in sorted(containers.items())
]

html_body = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;font-size:13px;color:#333;
                   max-width:820px;margin:0 auto;padding:24px;">
  <h1 style="color:#1a1a2e;border-bottom:3px solid #2c7bb6;padding-bottom:8px;margin-bottom:4px;">
    RKTB Daily Health Digest
  </h1>
  <p style="color:#888;margin-top:4px;">{timestamp_s} &mdash; Last 24 hours</p>

  <div style="background:{'#fff3f3' if error_count > 0 else '#f0fff0'};
              border:1px solid {'#ffcccc' if error_count > 0 else '#ccffcc'};
              border-radius:6px;padding:12px 18px;margin:20px 0;font-size:14px;">
    <strong style="color:{err_color};">{err_icon} {error_count} error(s)</strong>
    &nbsp;&nbsp;|&nbsp;&nbsp;{warning_count} warning(s)
    &nbsp;&nbsp;|&nbsp;&nbsp;{analyses_total} analyses
    &nbsp;&nbsp;|&nbsp;&nbsp;{cache_hits} cache hits
  </div>

  {section_html("📊 Container Health (now)", table(container_rows) if container_rows else "<p>No data</p>")}

  {section_html("📈 Backend Memory — 24h Trend", table([
      ("Current",      fmt_mb(containers.get('rktb-backend-1', {}).get('mem_mb'))),
      ("24h minimum",  fmt_mb(mem_min)),
      ("24h average",  fmt_mb(mem_avg)),
      ("24h maximum",  fmt_mb(mem_max)),
      ("Growth (max − min)", fmt_mb(mem_growth) if mem_growth is not None else "N/A"),
  ]))}

  {section_html("🔍 Analysis Activity", table([
      ("Fresh LLM analyses",  str(analyses_total)),
      ("Cache hits",          str(cache_hits)),
      ("Partial failures",    str(partial_failures)),
  ]))}

  {section_html("🔒 Auth Activity", table([
      ("Failed login attempts", str(failed_logins)),
      ("Accounts locked",       str(locked_accounts)),
  ]))}

  {section_html("⚙️ Background Jobs & Maintenance", table([
      (f"{rst_icon} Daily restart (21:00 UTC)", restart_note[:160]),
      ("Guests cleaned up",    guest_cleanup),
      ("Prompt logs purged",   prompt_cleanup),
  ]))}

  {section_html("📁 Prompt Logs & Disk", table([
      ("Prompt files saved today",   str(today_prompts)),
      ("logs/ total disk usage",     logs_disk),
      ("docker_stats.log size",      stats_log_size),
  ]))}

  {section_html("⚠️ Top Error Patterns", ul(top_errors, "No errors — all clear!"), color="#cc0000")}

  {section_html("Top Warning Patterns", ul(top_warnings, "No warnings"), color="#888")}

  <hr style="border:none;border-top:1px solid #eee;margin-top:36px;"/>
  <p style="color:#bbb;font-size:11px;">RKTB Monitoring · rkteambuilder.com</p>
</body></html>"""

text_body = f"""RKTB Daily Health Digest — {timestamp_s}

{err_icon} ERRORS (24h): {error_count}    WARNINGS: {warning_count}

ANALYSES: {analyses_total} fresh  |  {cache_hits} cache hits  |  {partial_failures} partial failures
AUTH:     {failed_logins} failed logins  |  {locked_accounts} locked accounts

CONTAINER HEALTH (current):
{chr(10).join(f'  {n}: {s["mem_raw"]}  CPU: {s["cpu"]}' for n, s in sorted(containers.items()))}

BACKEND MEMORY (24h): min={fmt_mb(mem_min)}  avg={fmt_mb(mem_avg)}  max={fmt_mb(mem_max)}  growth={fmt_mb(mem_growth)}

{rst_icon} DAILY RESTART: {restart_note[:160]}
GUESTS CLEANED:   {guest_cleanup}
PROMPT FILES TODAY: {today_prompts}
LOGS DISK USAGE:  {logs_disk}
DOCKER_STATS.LOG: {stats_log_size}

TOP ERRORS:
{chr(10).join(f'  {msg[:90]} x{cnt}' for msg, cnt in top_errors) or '  None'}

TOP WARNINGS:
{chr(10).join(f'  {msg[:90]} x{cnt}' for msg, cnt in top_warnings) or '  None'}
"""

# ── 7. Send ───────────────────────────────────────────────────────────────────

print("Sending digest email...")
subject = f"[RKTB Daily] {'⚠ ' + str(error_count) + ' error(s)' if error_count else '✓ All clear'} — {TODAY}"

payload = json.dumps({
    "from":    "noreply@rkteambuilder.com",
    "to":      ["shenhaoting@gmail.com"],
    "subject": subject,
    "html":    html_body,
    "text":    text_body,
}).encode()

req = urllib.request.Request("https://api.resend.com/emails", data=payload,
    headers={
        "Authorization":  f"Bearer {API_KEY}",
        "Content-Type":   "application/json",
        "User-Agent":     "curl/7.81.0",
    })
try:
    resp = urllib.request.urlopen(req, timeout=15)
    print(f"Digest sent — HTTP {resp.status}")
except urllib.error.HTTPError as e:
    body = e.read().decode(errors="replace")
    print(f"Failed to send digest: HTTP {e.code} — {body}")
except Exception as e:
    print(f"Failed to send digest: {e}")
