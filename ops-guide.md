# Production Operations Guide

**Site:** rkteambuilder.com
**Stack:** CloudFront → EC2 (FastAPI + Redis in Docker) + RDS PostgreSQL + S3
**SSH:** `ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192`

---

## Scenarios

1. [You Found a Bug — Fix and Deploy](#scenario-1-you-found-a-bug--fix-and-deploy)
2. [Site Is Down / Users Reporting Errors](#scenario-2-site-is-down--users-reporting-errors)
3. [Managing Users](#scenario-3-managing-users)
4. [Updating Game Data (New Monsters, Moves, etc.)](#scenario-4-updating-game-data-new-monsters-moves-etc)
5. [Database Schema Changed (New Migration)](#scenario-5-database-schema-changed-new-migration)
6. [Something Costs Too Much](#scenario-6-something-costs-too-much)
7. [Email Not Being Sent](#scenario-7-email-not-being-sent)
8. [Update an Environment Variable or Secret](#scenario-8-update-an-environment-variable-or-secret)
9. [Adjust Rate Limits or Tier Quotas](#scenario-9-adjust-rate-limits-or-tier-quotas)
10. [Rollback a Bad Deployment](#scenario-10-rollback-a-bad-deployment)
11. [Viewing and Managing Prompt Logs](#scenario-11-viewing-and-managing-prompt-logs)

---

## The Two-Minute Mental Model

```
Your laptop
  └── git push → GitHub Actions (runs tests → builds → deploys)
                      └── EC2: pulls new Docker image, restarts containers
                      └── S3: uploads new frontend build
                      └── CloudFront: cache invalidated

Users → CloudFront → S3 (frontend HTML/JS)
                   → EC2/Nginx → FastAPI (API calls)
                              → RDS (database)
                              → Redis (cache + rate limits)
```

**Key insight:** Almost everything is automated via `git push`. You only SSH into EC2 for logs, scripts, or emergencies.

---

## Scenario 1: You Found a Bug — Fix and Deploy

### Normal bug (code fix)

```bash
# Fix the bug locally, then:
git add .
git commit -m "Fix: describe what was broken"
git push origin main
```

GitHub Actions automatically:
1. Runs backend tests (`pytest`) and frontend checks (`typecheck`, `lint`)
2. If tests pass → builds new Docker image → pushes to ECR
3. Deploys to EC2 (pulls new image, restarts containers)
4. Uploads new frontend to S3, invalidates CloudFront cache

**Monitor the deployment:**
Go to GitHub → Actions tab → watch the running workflow. Takes ~5-8 minutes total.

**Verify it worked:**
```bash
curl https://rkteambuilder.com/health
# Expected: {"status": "healthy"}
```

### If tests are failing in CI but work locally

Check the Actions tab for the exact error. Common causes:
- Unused import or variable (ESLint strict)
- Type error that TypeScript catches in CI but not locally
- A test that depends on external state

Fix the code, push again. Don't skip tests (`--no-verify`) to force it through.

### Hotfix: CI is broken and you need a patch live NOW

Only do this if the bug is severe and CI is broken for unrelated reasons:
```bash
# SSH into EC2 and manually restart with the last known-good image
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb
docker compose -f docker-compose.prod.yml restart backend
```
This doesn't deploy new code — it just restarts what's already running.

---

## Scenario 2: Site Is Down / Users Reporting Errors

### Step 1: Quick diagnosis

```bash
# Is the site reachable at all?
curl -I https://rkteambuilder.com
curl https://rkteambuilder.com/health
```

- **curl times out** → CloudFront or EC2 is down
- **health returns 200** → EC2 is fine, issue is in the app logic
- **health returns 5xx** → backend is up but broken (DB or Redis likely)

### Step 2: SSH and check containers

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb

# Are containers running?
docker ps

# View recent logs (last 100 lines)
docker compose -f docker-compose.prod.yml logs --tail=100 backend

# Follow live logs
docker compose -f docker-compose.prod.yml logs -f backend
```

Look for: exceptions, `ERROR`, database connection errors, Redis errors.

### Step 3: Common fixes

**Backend container crashed:**
```bash
docker compose -f docker-compose.prod.yml up -d
```

**Database connection refused:**
- Check RDS is running: AWS Console → RDS → rktb-postgres → status should be "Available"
- If stopped: `aws rds start-db-instance --db-instance-identifier rktb-postgres --region ap-southeast-1`

**Redis is down:**
```bash
docker compose -f docker-compose.prod.yml restart redis
# Then restart backend so it reconnects
docker compose -f docker-compose.prod.yml restart backend
```

**Something broke after a deployment:**
```bash
# Roll back to the previous Docker image (uses :latest tag from before)
# Find the previous image tag from GitHub Actions history, then:
docker pull 273130558025.dkr.ecr.ap-southeast-1.amazonaws.com/rktb-backend:<previous-sha>
# Edit docker-compose.prod.yml IMAGE_TAG and restart
```

---

## Scenario 3: Managing Users

Use the Swagger UI at **rkteambuilder.com/docs** while logged in as admin (shenhaoting@gmail.com). No SSH needed.

### Find a user
```
GET /admin/users?search=email@example.com
```

### User claims they hit quota unfairly
```
GET /admin/users/{user_id}         # Check their tier and usage
PUT /admin/users/{user_id}/tier    # Bump to premium if warranted
  Body: {"tier": "premium"}
```

### Abusive or spamming user
```
POST /admin/users/{user_id}/lock
  Body: {"reason": "abuse", "duration_minutes": 10080}   # 7 days
```

### Delete a test account you created
```
DELETE /admin/users/{user_id}
  Body: {"delete_teams": true, "add_email_cooldown": false}
```

### See overall site activity
```
GET /admin/stats    # Total users, teams, analyses this month
```

---

## Scenario 4: Updating Game Data (New Monsters, Moves, etc.)

Data lives in your JSON files. When the game updates:

1. Update the JSON data files locally
2. Push to git (this deploys new code, but **does not** re-import data)
3. SSH in and run the importer:

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192

# Get into the backend container
docker exec -it rktb-backend bash

# You're now at /app inside the container
# Run specific importers (safe, won't touch user data):
python3 -m backend.scripts.importers.import_monsters
python3 -m backend.scripts.importers.import_moves
python3 -m backend.scripts.importers.import_traits

# Or nuclear reset of ALL game data (preserves users/teams):
python3 -m backend.scripts.importers.reset_and_reimport

# Exit container
exit
```

> After re-importing game data, clear the LLM cache so analyses reflect the new data:
> ```bash
> docker exec -it rktb-backend bash
> # Run a quick Redis flush of cache keys only (not rate limit keys)
> # Or just wait 1 hour for cache to naturally expire (TTL=3600s)
> ```

### Check what's in the database
```bash
docker exec -it rktb-backend bash
python3 -m backend.scripts.validation.count_table_records
```

---

## Scenario 5: Database Schema Changed (New Migration)

This is the most sensitive operation — do it carefully.

```bash
# 1. Locally: generate migration after editing models.py
cd backend
source ~/.venvs/rktb310/bin/activate
alembic revision --autogenerate -m "add column X to table Y"

# 2. Review the generated file in backend/alembic/versions/
# Make sure it only changes what you intended

# 3. Push to git — this deploys new code but does NOT run migrations
git push origin main

# 4. After deployment succeeds, SSH in and run migration
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
docker exec -it rktb-backend bash
cd /app
alembic upgrade head

# 5. Verify
alembic current    # Should show your new migration as (head)
exit
```

**If migration fails:**
```bash
alembic downgrade -1    # Roll back one step
```

> Never run `reset_and_reimport` after a schema change without also running migrations first — the importer assumes the schema is up to date.

---

## Scenario 6: Something Costs Too Much

### Check current spend
```bash
aws ce get-cost-and-usage \
  --time-period Start=2026-02-01,End=2026-03-01 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --region us-east-1
```

### Temporarily pause the site (stop billing)
```bash
# Stop EC2 (~$8/month saved)
aws ec2 stop-instances --instance-ids i-08477110ddb42c54d --region ap-southeast-1

# Stop RDS (~$15/month saved) — takes ~2 min
aws rds stop-db-instance --db-instance-identifier rktb-postgres --region ap-southeast-1
```

> RDS auto-restarts after 7 days (AWS limitation). You'll need to stop it again.

### Restart everything
```bash
aws rds start-db-instance --db-instance-identifier rktb-postgres --region ap-southeast-1
# Wait ~3 minutes for RDS to be "Available", then:
aws ec2 start-instances --instance-ids i-08477110ddb42c54d --region ap-southeast-1
```

### DeepSeek costs too much (LLM calls)
- Each team analysis = 7 LLM calls
- Adjust quota limits in Parameter Store to reduce usage per tier
- Or switch to a cheaper model: change `DEEPSEEK_MODEL` in Parameter Store

---

## Scenario 7: Email Not Being Sent

```bash
# Check if SMTP is configured in the container
docker exec rktb-backend env | grep SMTP

# Trigger a test (register a new account or request password reset)
# Then check logs immediately:
docker compose -f docker-compose.prod.yml logs --tail=50 backend | grep -i email
```

**If you see `[EMAIL-DEV] SMTP not configured`:**
The SMTP parameters are missing from Parameter Store. Re-add them and restart.

**If you see SMTP errors:**
- Check Resend dashboard for send failures
- Verify API key is valid: Resend → API Keys
- Verify DNS records are still set up: Cloudflare → rkteambuilder.com → DNS

---

## Scenario 8: Update an Environment Variable or Secret

Never edit `docker-compose.prod.yml` directly for secrets — always use Parameter Store.

```bash
# Example: update DeepSeek API key
aws ssm put-parameter \
  --name /rktb/prod/DEEPSEEK_API_KEY \
  --value "sk-new-key-here" \
  --type SecureString \
  --overwrite \
  --region ap-southeast-1

# Then redeploy so containers pick up the new value
# Option A: push a trivial commit to trigger CI/CD
# Option B: SSH and manually re-run deploy.sh
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb
bash deploy.sh latest
```

**Add a new admin email:**
```bash
aws ssm put-parameter \
  --name /rktb/prod/ADMIN_EMAILS \
  --value "shenhaoting@gmail.com,other@example.com" \
  --type String \
  --overwrite \
  --region ap-southeast-1
# Then restart backend
```

---

## Scenario 9: Adjust Rate Limits or Tier Quotas

All quota values are env vars — change in Parameter Store + restart.

```bash
# Example: free tier users get more daily analyses
aws ssm put-parameter \
  --name /rktb/prod/TIER_FREE_DAILY_ANALYSES \
  --value "10" \
  --type String \
  --overwrite \
  --region ap-southeast-1

# Restart backend to pick up changes
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb
docker compose -f docker-compose.prod.yml restart backend
```

Rate limit env vars (in `config.py`):
- `TIER_ANONYMOUS_DAILY_ANALYSES` / `TIER_ANONYMOUS_MONTHLY_ANALYSES`
- `TIER_GUEST_DAILY_ANALYSES` / `TIER_GUEST_MONTHLY_ANALYSES`
- `TIER_FREE_DAILY_ANALYSES` / `TIER_FREE_MONTHLY_ANALYSES`
- `TIER_PREMIUM_DAILY_ANALYSES` / `TIER_PREMIUM_MONTHLY_ANALYSES`
- `ANALYSIS_RATE_LIMIT` — IP-based throttle (e.g., `"1/2minutes"`)

---

## Scenario 10: Rollback a Bad Deployment

Rollback means reverting to the previous working version when a deployment breaks production. Your stack has three separate things to roll back, each with different difficulty.

### Decision tree

```
Deployment broke something?
  │
  ├── Frontend visual bug / logic bug with no schema change
  │     → Just fix forward: git push a fix (5-8 min). Fastest option.
  │
  ├── Backend crash, no migration ran
  │     → Roll back Docker image to previous SHA (see below)
  │
  └── Migration ran AND new code is broken
        → Roll back migration first, then roll back Docker image
```

### Roll back the backend (Docker image)

Every deployment tags the Docker image with the git commit SHA. Old images stay in ECR, so you can revert:

```bash
# 1. Find the previous working SHA
#    GitHub → Actions → find the last green deployment → copy the commit SHA

# 2. SSH into EC2
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb

# 3. Deploy the old image by passing the old SHA to deploy.sh
bash deploy.sh <previous-sha>
```

### Roll back the frontend (S3)

CI/CD deploys with `--delete` so the old build is gone from S3. To restore:

**Option A — Re-run old workflow (easiest):**
GitHub → Actions → find the last green deployment run → top-right "Re-run jobs" → "Re-run all jobs"

**Option B — Build locally from old commit:**
```bash
git checkout <previous-sha>
cd frontend && npm run build
aws s3 sync dist/ s3://rktb-frontend --delete --region ap-southeast-1
aws cloudfront create-invalidation --distribution-id E1S4H9ALERPPY0 --paths "/*" --region us-east-1
git checkout main
```

### Roll back a database migration (hardest)

If a migration ran and the code is broken, rolling back code alone won't fix it — the old code won't understand the new schema.

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
docker exec -it rktb-backend bash

# Check current state
alembic current

# Undo the last migration
alembic downgrade -1

# Verify
alembic current
exit
```

Then roll back the Docker image as above so the old code matches the old schema.

> **This is why migrations deserve their own commit.** If schema changes and code changes are in separate commits, you can roll back one without the other.

### What rollback looks like in practice (at your scale)

Companies with thousands of users treat rollback as a fire drill — every second matters. For your site, the realistic scenario is:

- You push, notice something broken in logs or via a user report
- If it's a simple bug: **fix forward** with another `git push` in 5 minutes — faster than a formal rollback
- If the site is completely broken: use the Docker image rollback above
- Database rollbacks are rare and only needed if a migration itself was wrong

The golden rule: **never run a risky migration and a big code change in the same commit.**

---

## Scenario 11: Viewing and Managing Prompt Logs

Every LLM analysis is logged to `/home/ubuntu/rktb/logs/prompts/` on EC2, organized by date. Logs older than 30 days are automatically deleted by a background task at startup.

### Browse logs on EC2

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192

# List available dates
ls /home/ubuntu/rktb/logs/prompts/

# List all files for a specific day
ls /home/ubuntu/rktb/logs/prompts/2026-02-26/

# Read a specific log file
cat /home/ubuntu/rktb/logs/prompts/2026-02-26/14-30-05_trait_synergy_Flamewing_en_miss.txt

# Count how many analyses were run today
ls /home/ubuntu/rktb/logs/prompts/$(date +%Y-%m-%d)/ | wc -l

# Check total disk usage of all logs
du -sh /home/ubuntu/rktb/logs/prompts/
```

### Copy logs to your local machine

```bash
# Run from your local WSL terminal — copies all logs, skips files already downloaded
rsync -avz -e "ssh -i ~/.ssh/rktb-key.pem" \
  ubuntu@13.228.63.192:/home/ubuntu/rktb/logs/prompts/ \
  "/mnt/d/Alan/Github Projects/roco-kingdom-team-builder/backend/logs/prompts/"
```

### Manually delete old logs (if disk fills up unexpectedly)

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
docker exec -it rktb-backend bash
python3 -c "from backend.prompt_logger import clear_old_logs; print(clear_old_logs(days=7), 'files deleted')"
exit
```

### Log filename format

```
HH-MM-SS_<context>_<monster>_<language>_<cache_status>.txt
Example: 14-30-05_trait_synergy_Flamewing_en_miss.txt
         14-30-06_team_synergy_en_miss.txt
```

Each file contains: metadata, token usage, DeepSeek cache hit rate, response time, system prompt, and user prompt.

---

## Deployment Checklist (Before Pushing to Main)

- [ ] Run `cd backend && pytest -v` locally — all tests pass
- [ ] Run `cd frontend && npm run typecheck && npm run lint` — no errors
- [ ] If schema changed: migration file generated and reviewed
- [ ] If adding env vars: added to Parameter Store AND `docker-compose.prod.yml`
- [ ] If changing game data logic: plan to re-run importers after deploy

---

## Quick Reference

| Task | Method |
|---|---|
| Check site health | `curl https://rkteambuilder.com/health` |
| Deploy new code | `git push origin main` |
| View live logs | SSH → `docker compose -f docker-compose.prod.yml logs -f backend` |
| Restart backend | SSH → `docker compose -f docker-compose.prod.yml restart backend` |
| Manage users | `rkteambuilder.com/docs` (admin endpoints) |
| Run data scripts | SSH → `docker exec -it rktb-backend bash` → `python3 -m backend.scripts...` |
| Run migrations | SSH → `docker exec -it rktb-backend bash` → `alembic upgrade head` |
| Change a secret | AWS Parameter Store → put-parameter → restart backend |
| Browse prompt logs | SSH → `ls /home/ubuntu/rktb/logs/prompts/` |
| Backup prompt logs locally | `rsync -avz -e "ssh -i ~/.ssh/rktb-key.pem" ubuntu@13.228.63.192:/home/ubuntu/rktb/logs/prompts/ ~/rktb-logs/` |
| Stop billing | `aws ec2 stop-instances` + `aws rds stop-db-instance` |
| Check AWS costs | AWS Console → Billing → Cost Explorer |

## AWS Resource IDs

| Resource | ID |
|---|---|
| EC2 Instance | i-08477110ddb42c54d |
| EC2 Elastic IP | 13.228.63.192 |
| RDS Identifier | rktb-postgres |
| S3 Bucket | rktb-frontend |
| CloudFront ID | E1S4H9ALERPPY0 |
| Region | ap-southeast-1 |
