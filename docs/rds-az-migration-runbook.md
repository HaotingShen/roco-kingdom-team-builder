# RDS AZ Migration Runbook

> ✅ **EXECUTED 2026-04-04; old `rktb-postgres` instance deleted 2026-04-11.**
> Historical artifact — kept as a template for future snapshot-restore
> migrations. Current instance: `rktb-postgres-1a` in ap-southeast-1a.
> ⚠️ Contains the live RDS master password in cleartext (also in
> umami-setup.md) — rotate or scrub if the repo's audience ever widens.

**Problem:** RDS is in `ap-southeast-1b`, EC2 is in `ap-southeast-1a`. Every DB query crosses AZs,
costing ~$130/month in inter-AZ transfer fees.

**Goal:** Move RDS to `ap-southeast-1a` to eliminate the cost entirely.

**Approach:** Stop backend first, then snapshot, then restore. This guarantees zero data drift
between the snapshot and the new instance. Trade-off is ~25–35 minutes of total downtime.
Plan for this in advance — announce maintenance to users if needed (use the announcement banner).

**Pinned image tag:** `6d5c9ae59820f159bcd53fee7f6e4831e8c99eca`
Every deploy step in this runbook uses this exact tag. The code version does not change —
only the database connection changes.

ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192 \
    "docker inspect \$(docker compose -f /home/ubuntu/rktb/docker-compose.prod.yml ps -q backend) --format '{{.Config.Image}}'" \
    | cut -d: -f2

**Avoid the automated backup window: 18:41–19:11 UTC.** Do not start the migration during
this window. RDS I/O spikes during automated snapshots.

**Recommended cutover window:** 21:00–23:00 UTC (05:00–07:00 CST) — lowest traffic period.

---

## Known facts (confirmed before writing this runbook)

| Item | Value |
|---|---|
| Old RDS identifier | `rktb-postgres` |
| Old RDS AZ | `ap-southeast-1b` |
| EC2 AZ | `ap-southeast-1a` |
| New RDS identifier | `rktb-postgres-1a` |
| Target AZ | `ap-southeast-1a` |
| Subnet group | `rktb-db-subnets` (spans both 1a and 1b — correct) |
| RDS security group | `sg-0eedc536da3a8f6fa` |
| RDS instance class | `db.t3.micro` |
| RDS parameter group | `default.postgres16` (no custom params — restore will match) |
| RDS deletion protection | **ON** — must be disabled before deletion |
| Pinned image | `6d5c9ae59820f159bcd53fee7f6e4831e8c99eca` |
| EC2 instance | `i-08477110ddb42c54d` / `13.228.63.192` |

---

## Pre-flight — save rollback values (local machine, read-only)

Run these before anything else. Save the output in a text file. You will paste these exact
values verbatim if you need to roll back.

```bash
# Save this output — needed for rollback
aws ssm get-parameter --name /rktb/prod/DATABASE_URL \
  --with-decryption --query Parameter.Value --output text --region ap-southeast-1

postgresql://rktb_admin:26c50b538a8a5444ff7458424d9b9d2209d773e0c592370e@rktb-postgres.cnwseow4y66l.ap-southeast-1.rds.amazonaws.com:5432/roco_kingdom

# Save this output — needed for rollback
aws ssm get-parameter --name /rktb/prod/UMAMI_DATABASE_URL \
  --with-decryption --query Parameter.Value --output text --region ap-southeast-1

postgresql://rktb_admin:26c50b538a8a5444ff7458424d9b9d2209d773e0c592370e@rktb-postgres.cnwseow4y66l.ap-southeast-1.rds.amazonaws.com:5432/umami?sslmode=require&connection_limit=5

```

Do not proceed until both values are saved somewhere you can access even if the site is down.

---

## Phase 1 — Stop backend and take snapshot

Downtime begins at Step 1.1. Umami and Redis remain running throughout.

### Step 1.1 — Stop backend only (on EC2)

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb
docker compose -f docker-compose.prod.yml stop backend
```

Verify it stopped:

```bash
docker compose -f docker-compose.prod.yml ps
```

Expected: `backend` shows `exited`, `redis` and `umami` show `running`.
The site now returns 502. Downtime has begun.

### Step 1.2 — Take snapshot immediately (local machine)

Because the backend is stopped, no app writes can reach the DB. This snapshot is a clean,
exact copy of all user data at the moment the backend was stopped.

```bash
aws rds create-db-snapshot \
  --db-instance-identifier rktb-postgres \
  --db-snapshot-identifier rktb-migrate-to-1a \
  --region ap-southeast-1
```

Poll until `available` before proceeding. Typically 3–5 minutes.

```bash
aws rds describe-db-snapshots \
  --db-snapshot-identifier rktb-migrate-to-1a \
  --region ap-southeast-1 \
  --query 'DBSnapshots[0].{Status:Status,Time:SnapshotCreateTime}' \
  --output json
```

Do not proceed to Phase 2 until Status is `available`.

---

## Phase 2 — Restore new instance into ap-southeast-1a (local machine)

This does not affect the old DB or any running service.

### Step 2.1 — Restore from snapshot

```bash
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier rktb-postgres-1a \
  --db-snapshot-identifier rktb-migrate-to-1a \
  --db-instance-class db.t3.micro \
  --availability-zone ap-southeast-1a \
  --db-subnet-group-name rktb-db-subnets \
  --vpc-security-group-ids sg-0eedc536da3a8f6fa \
  --no-multi-az \
  --no-publicly-accessible \
  --region ap-southeast-1
```

### Step 2.2 — Wait until available (~10–15 min)

```bash
aws rds describe-db-instances \
  --db-instance-identifier rktb-postgres-1a \
  --region ap-southeast-1 \
  --query 'DBInstances[0].{Status:DBInstanceStatus,AZ:AvailabilityZone,Endpoint:Endpoint.Address}' \
  --output json
```

Do not proceed until:
- `Status` is `available`
- `AZ` is `ap-southeast-1a`
- `Endpoint` is populated

**Copy the Endpoint value.** You will use it throughout Phase 3 and 4.

---

## Phase 3 — Validate new instance before switching production (on EC2)

Nothing in this phase writes to production SSM or modifies any service.
You are connecting directly to the new DB to confirm it is ready.

SSH to EC2 if not already there:

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
```

Set up connection strings. Replace `NEW_ENDPOINT_HERE` with the Endpoint from Step 2.2:

```bash
NEW_HOST="NEW_ENDPOINT_HERE"

OLD_DB=$(aws ssm get-parameter --name /rktb/prod/DATABASE_URL \
  --with-decryption --query Parameter.Value --output text --region ap-southeast-1)

NEW_DB=$(echo "$OLD_DB" | sed \
  "s|rktb-postgres\.cnwseow4y66l\.ap-southeast-1\.rds\.amazonaws\.com|$NEW_HOST|")

OLD_UMAMI=$(aws ssm get-parameter --name /rktb/prod/UMAMI_DATABASE_URL \
  --with-decryption --query Parameter.Value --output text --region ap-southeast-1)

NEW_UMAMI=$(echo "$OLD_UMAMI" | sed \
  "s|rktb-postgres\.cnwseow4y66l\.ap-southeast-1\.rds\.amazonaws\.com|$NEW_HOST|")

echo "NEW_DB:    $NEW_DB"
echo "NEW_UMAMI: $NEW_UMAMI"
```

Confirm both NEW lines show only the hostname changed. Everything else must be identical to OLD.

### Test 1 — Connectivity

```bash
psql "$NEW_DB" -c "SELECT 1 AS connection_test;"
```

Expected: one row, `connection_test = 1`.
**If this fails, stop. Do not proceed.** The new DB is not reachable. Check security group
`sg-0eedc536da3a8f6fa` allows inbound port 5432 from the EC2 security group.

### Test 2 — Schema version matches

```bash
echo "Old DB:" && psql "$OLD_DB" -t -c "SELECT version_num FROM alembic_version;"
echo "New DB:" && psql "$NEW_DB" -t -c "SELECT version_num FROM alembic_version;"
```

Expected: identical output on both lines.
**If they differ, stop.** The snapshot is inconsistent.

### Test 3 — All expected tables present

```bash
psql "$NEW_DB" -c "\dt public.*"
```

Expected: tables including `users`, `teams`, `user_monsters`, `monsters`, `moves`, `types`,
`traits`, `personalities`, `magic_items`, `game_terms`, `team_analyses`, `deleted_emails`,
`alembic_version`.
**If any critical table is missing, stop.**

### Test 4 — Row counts match between old and new

Because the backend was stopped before the snapshot, row counts must be **identical** for all
tables. Any difference indicates the snapshot was taken while writes were still in flight.

```bash
for table in users teams user_monsters team_analyses monsters moves types traits magic_items game_terms deleted_emails; do
  OLD_COUNT=$(psql "$OLD_DB" -t -c "SELECT COUNT(*) FROM $table;" | tr -d ' \n')
  NEW_COUNT=$(psql "$NEW_DB" -t -c "SELECT COUNT(*) FROM $table;" | tr -d ' \n')
  MATCH="OK"
  [ "$OLD_COUNT" != "$NEW_COUNT" ] && MATCH="MISMATCH"
  echo "$MATCH  $table: OLD=$OLD_COUNT  NEW=$NEW_COUNT"
done
```

Expected: every row shows `OK`. **If any row shows `MISMATCH`, stop and investigate.**

### Test 5 — Umami DB connectivity (SSL-faithful)

`connection_limit=5` is stripped because it is a Prisma-specific parameter that psql does not
understand. `sslmode=require` is preserved so this test validates the same SSL behavior the
app uses.

```bash
UMAMI_PSQL=$(echo "$NEW_UMAMI" | sed 's/&connection_limit=[^&?]*//')
psql "$UMAMI_PSQL" -c "SELECT COUNT(*) FROM website;"
```

Expected: returns a number (likely 1 — your single Umami website entry).
**If this fails, stop.**

### All five tests passed?

If yes, the new DB is confirmed reachable, schema-correct, and data-complete.
Proceed to Phase 4.

If any test failed, do not proceed. Delete the new instance and investigate:

```bash
aws rds delete-db-instance \
  --db-instance-identifier rktb-postgres-1a \
  --skip-final-snapshot \
  --region ap-southeast-1
```

Then restart the backend to end downtime:

```bash
# On EC2
bash deploy.sh 6d5c9ae59820f159bcd53fee7f6e4831e8c99eca
```

---

## Phase 4 — Cut over to new DB (local machine + EC2)

### Step 4.1 — Build and verify new SSM values before writing

On your local machine. `NEW_HOST`, `NEW_DB`, `NEW_UMAMI` must be set (re-run the Phase 3
setup block in a new terminal if needed, substituting the same `NEW_ENDPOINT_HERE`).

```bash
echo "=== Verify before writing ==="
echo "DATABASE_URL OLD:    $OLD_DB"
echo "DATABASE_URL NEW:    $NEW_DB"
echo ""
echo "UMAMI_DATABASE_URL OLD: $OLD_UMAMI"
echo "UMAMI_DATABASE_URL NEW: $NEW_UMAMI"
```

Check each NEW line:
- Only the hostname changed
- Port `:5432` still present
- Database name (`roco_kingdom` / `umami`) still correct
- `?sslmode=require&connection_limit=5` still present in the Umami URL

**Do not write to SSM if anything else changed.**

### Step 4.2 — Write new SSM values

```bash
aws ssm put-parameter --name /rktb/prod/DATABASE_URL \
  --value "$NEW_DB" --type SecureString --overwrite --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/UMAMI_DATABASE_URL \
  --value "$NEW_UMAMI" --type SecureString --overwrite --region ap-southeast-1
```

### Step 4.3 — Redeploy with pinned image (on EC2)

Uses the exact same code version that was running before. Only the DB connection changes.
Alembic will run `upgrade head` — this is a confirmed no-op since the schema already matches.

```bash
bash deploy.sh 6d5c9ae59820f159bcd53fee7f6e4831e8c99eca
```

### Step 4.4 — Verify immediately after deploy

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --since 3m backend | \
  grep -E "(ERROR|started|Uvicorn|database|connection|Alembic)"
```

Expected: all containers running, no ERROR lines, Uvicorn shows it started successfully.

### Step 4.5 — Smoke test (within 5 minutes of deploy)

1. Load `https://rkteambuilder.com` — page must load
2. Log in with an existing account — must succeed (confirms users table readable)
3. Open Saved Teams — existing teams must appear (confirms teams table readable)
4. Open the Dex — monsters must load (confirms monsters table readable)
5. Save a small team change — confirms write path works
6. Load `https://analytics.rkteambuilder.com` — Umami dashboard must load

If all six pass, downtime is over. The migration is complete.

---

## Rollback — if anything fails in Phase 4

Run these in order. Do not skip steps.

```bash
# R1 — Restore old DATABASE_URL (paste exact value saved in Pre-flight)
aws ssm put-parameter --name /rktb/prod/DATABASE_URL \
  --value "PASTE_EXACT_OLD_VALUE_HERE" \
  --type SecureString --overwrite --region ap-southeast-1

# R2 — Restore old UMAMI_DATABASE_URL (paste exact value saved in Pre-flight)
aws ssm put-parameter --name /rktb/prod/UMAMI_DATABASE_URL \
  --value "PASTE_EXACT_OLD_VALUE_HERE" \
  --type SecureString --overwrite --region ap-southeast-1

# R3 — Redeploy with pinned image pointing back to old DB
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192 \
  "cd /home/ubuntu/rktb && bash deploy.sh 6d5c9ae59820f159bcd53fee7f6e4831e8c99eca"

# R4 — Confirm containers are running
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192 \
  "cd /home/ubuntu/rktb && docker compose -f docker-compose.prod.yml ps"

# R5 — Confirm no errors in logs
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192 \
  "cd /home/ubuntu/rktb && docker compose -f docker-compose.prod.yml logs --since 3m backend"
```

After rollback, repeat the six smoke tests from Step 4.5. The old DB (`rktb-postgres` in 1b)
was never modified — all data is intact.

---

## Phase 5 — Delete old instance (24–48 hours after successful cutover)

Wait at least 24 hours of confirmed normal operation before this phase. Check the daily
monitoring email digest and confirm no DB errors appeared.

### Step 5.1 — Take final snapshot of old instance

This captures any state that existed in the old instance before permanent deletion.
Belt-and-suspenders: you already have `rktb-migrate-to-1a` but this gives you a final
checkpoint.

```bash
aws rds create-db-snapshot \
  --db-instance-identifier rktb-postgres \
  --db-snapshot-identifier rktb-postgres-final-before-deletion \
  --region ap-southeast-1
```

Wait until `available`:

```bash
aws rds describe-db-snapshots \
  --db-snapshot-identifier rktb-postgres-final-before-deletion \
  --region ap-southeast-1 \
  --query 'DBSnapshots[0].Status' \
  --output text
```

### Step 5.2 — Disable deletion protection

```bash
aws rds modify-db-instance \
  --db-instance-identifier rktb-postgres \
  --no-deletion-protection \
  --apply-immediately \
  --region ap-southeast-1
```

### Step 5.3 — Delete old instance

> ⚠️ DESTRUCTIVE AND IRREVERSIBLE. The instance `rktb-postgres` will be permanently deleted.
> Your snapshots remain until you explicitly delete them.

```bash
aws rds delete-db-instance \
  --db-instance-identifier rktb-postgres \
  --final-db-snapshot-identifier rktb-postgres-pre-delete-final \
  --region ap-southeast-1
```

Takes 5–10 minutes. The `--final-db-snapshot-identifier` causes AWS to take one more
automated snapshot before deletion.

### Step 5.4 — Enable deletion protection on new instance

```bash
aws rds modify-db-instance \
  --db-instance-identifier rktb-postgres-1a \
  --deletion-protection \
  --apply-immediately \
  --region ap-southeast-1
```

---

## What changes and what does not

| Component | Changed? | Notes |
|---|---|---|
| Application code | No | Same pinned image throughout |
| Database schema | No | Snapshot restore is schema-identical |
| All user accounts | No | Captured in snapshot taken after backend stopped |
| All saved teams | No | Captured in snapshot taken after backend stopped |
| All team analyses | No | Captured in snapshot taken after backend stopped |
| JWT blacklist (Redis) | No | Redis is not affected |
| Quota counters (Redis) | No | Redis is not affected |
| Umami analytics history | No | Captured in snapshot |
| Umami events during downtime | Lost | Acceptable — analytics only |
| CloudFront, S3, nginx | No | Not involved |
| SSM secrets (except DB URLs) | No | Only DATABASE_URL and UMAMI_DATABASE_URL change |
| Monthly inter-AZ cost | Eliminated | ~$130/month saved |

## Estimated downtime

| Step | Time |
|---|---|
| Stop backend | <1 min |
| Snapshot completes | 3–5 min |
| Restore completes | 10–15 min |
| Validation (Phase 3) | 5 min |
| SSM write + deploy + verify | 3–5 min |
| **Total** | **~25–35 min** |
