# Local Development & Deployment Guide

A step-by-step reference for developing new features locally and deploying them to production.

---

## Overview of the Flow

```
1. Start local environment
2. Create a feature branch
3. Write & test the feature locally
4. Verify (typecheck, lint, tests)
5. Merge to main → auto-deploys to production
6. Verify in production
```

---

## Part 1: Starting Your Local Environment

You need four things running: PostgreSQL, Redis, the backend, and the frontend.

### Step 1 — Start Redis (via Docker)

```bash
# From project root
docker compose up -d redis
```

> **What this does:** Starts a Redis container on your machine at `localhost:6379`.
> This is completely separate from production Redis on EC2. No interference.
>
> **Check it's running:**
> ```bash
> docker compose ps
> ```
> You should see `redis` with status `running`.

### Step 2 — Ensure PostgreSQL is running

Your local backend connects to `postgresql+psycopg2://roco_user:0605@localhost/roco_db` (from `backend/.env`).

Make sure your local PostgreSQL service is running. On WSL2:
```bash
sudo service postgresql start
```

> **If the database doesn't exist yet**, create it:
> ```bash
> psql -U postgres -c "CREATE USER roco_user WITH PASSWORD '0605';"
> psql -U postgres -c "CREATE DATABASE roco_db OWNER roco_user;"
> ```
> Then run migrations (see below).

### Step 3 — Run database migrations

Whenever you pull new code or after creating a new migration:

```bash
source ~/.venvs/rktb310/bin/activate
cd backend
alembic upgrade head
cd ..
```

> **Warning:** Always run `alembic upgrade head` after pulling from main. If a teammate (or you, on another machine) added a migration, skipping this causes confusing errors.

### Step 4 — Start the backend

```bash
source ~/.venvs/rktb310/bin/activate
python3 -m uvicorn backend.main:app --reload --env-file backend/.env
```

The backend runs at `http://localhost:8000`. The `--reload` flag auto-restarts on code changes.

> **API docs available at:** `http://localhost:8000/docs` — very useful for testing endpoints manually.

> **Warning:** If you see a Redis connection error on startup, Redis isn't running. Go back to Step 1.

### Step 5 — Start the frontend

In a separate terminal:

```bash
cd frontend
npm run dev
```

Frontend runs at `http://localhost:5173`.

> **How API calls work locally:** The frontend calls `http://localhost:8000` directly (no proxy). This is set in `frontend/src/lib/api.ts` — it defaults to `localhost:8000` when `VITE_API_BASE_URL` is not set. In production, `VITE_API_BASE_URL=https://rkteambuilder.com/api` is injected at build time by GitHub Actions.

> **How images work locally:** Monster sprites, type icons, and magic item images are served from `frontend/public/` by Vite — same files that get uploaded to S3 on deploy. No extra setup needed.

### What doesn't work locally (and why it's fine)

| Feature | Status locally | Why |
|---|---|---|
| Email (verification, password reset) | ✅ Works | Resend SMTP credentials configured in `.env` — sends real emails from `noreply@rkteambuilder.com` |
| CAPTCHA | ✅ Disabled | `CAPTCHA_ENABLED=false` in `.env` |
| LLM analysis | ✅ Works | Gemini API key configured in `.env` |
| Redis caching/quota | ✅ Works | Local Redis via Docker |
| Authentication | ✅ Works | Local JWT with local secret key |
| CloudFront caching | N/A | Not applicable locally |
| Umami analytics | ⚠️ Sends to production | The `<script>` in `index.html` points to `analytics.rkteambuilder.com` (fully deployed at `analytics.rkteambuilder.com`). Local dev visits are tracked in your real dashboard. To prevent this, go to `https://analytics.rkteambuilder.com`, click your username → **Ignore my visits** on this device. |


---

## Part 2: Writing a New Feature

### Always work on a feature branch

```bash
# Create and switch to a new branch
git checkout -b feature/your-feature-name

# Example:
git checkout -b feature/team-share
```

> **Why:** Pushing to `main` triggers an immediate production deployment. Working on a branch keeps production safe while you develop.

> **Never push unfinished features directly to `main`.**

### Adding new backend dependencies

```bash
source ~/.venvs/rktb310/bin/activate
pip install some-package
pip freeze > backend/requirements.txt  # update requirements so Docker picks it up
```

> **Warning:** If you forget to update `requirements.txt`, the local backend works but the Docker build in CI will fail because the package isn't installed in the container.

### Adding new frontend dependencies

```bash
cd frontend
npm install some-package
```

The `package-lock.json` updates automatically. Commit both `package.json` and `package-lock.json`.

> **Warning:** CI uses `npm ci` (not `npm install`), which requires `package-lock.json` to be in sync. Always commit it.

### Adding new database columns or tables

```bash
source ~/.venvs/rktb310/bin/activate

# 1. Edit backend/models.py to add your new model/column
# 2. Generate a migration:
cd backend
alembic revision --autogenerate -m "add share_tokens table"

# 3. Review the generated file in backend/alembic/versions/
#    Make sure it looks correct — autogenerate isn't perfect

# 4. Apply locally:
alembic upgrade head
```

> **Warning:** Alembic autogenerate misses some things (e.g. changes to `Enum` types, index changes on existing columns, changes inside JSONB). Always read the generated migration file before applying.

> **Production note:** Migrations run automatically on deploy via `deploy.sh`. You do NOT need to manually SSH in to run migrations. But if a migration is destructive (drops a column), make sure no old code is still reading that column before deploying.

### Adding new environment variables

1. Add the variable to `backend/.env` locally with a test value
2. Add the variable to `backend/config.py` (where all env vars are read)
3. Add the production value to AWS Parameter Store:
   ```bash
   aws ssm put-parameter \
     --name /rktb/prod/YOUR_NEW_VAR \
     --value "production-value" \
     --type SecureString \
     --region ap-southeast-1
   ```
4. Add it to `deploy.sh` on EC2 so it's injected into Docker at startup

> **Warning:** Forgetting step 4 means the variable exists in Parameter Store but never reaches the running container. The backend will either crash or silently use a default value.

---

## Part 3: Testing Locally

### Run backend tests

```bash
source ~/.venvs/rktb310/bin/activate
cd backend && pytest -v
```

### Run frontend checks

```bash
cd frontend
npm run typecheck   # TypeScript type checking
npm run lint        # ESLint
```

> **Important:** CI runs both of these before every deploy. If they fail locally, they'll fail in CI and block the deploy. Fix them before pushing to main.

### Test the feature manually

1. Open `http://localhost:5173`
2. Use the feature as a real user would
3. Check `http://localhost:8000/docs` to test backend endpoints directly
4. Watch the backend terminal for errors/tracebacks

### Checking for production-parity issues

Things to double-check before deploying a new feature:

- **HTTPS-only cookies:** Locally `COOKIE_SECURE=false`, production `COOKIE_SECURE=true`. If you set a cookie without `secure=True` in code, it still works locally but may behave differently in production. Check any new cookie code.
- **CORS:** New endpoints don't need CORS config (FastAPI uses the global `ALLOWED_ORIGINS`), but if you add a new frontend origin, update `ALLOWED_ORIGINS` in `.env` and in production Parameter Store.
- **Two uvicorn workers:** Production runs `--workers 2`. If your feature uses any in-memory state (a global variable, a dict), it won't be shared between workers. Use Redis for any shared state. This is a common source of "works locally, breaks in production" bugs.
- **CloudFront caching:** The frontend is cached at the edge. CI invalidates the cache on every deploy (`aws cloudfront create-invalidation --paths "/*"`). You don't need to do this manually, but it means there can be a 1-2 min delay after deploy before all users see the new frontend.

---

## Part 4: Deploying to Production

### Step 1 — Final local checks

```bash
# Run everything one more time
cd backend && pytest -v
cd ../frontend && npm run typecheck && npm run lint
```

### Step 2 — Commit your changes

```bash
git add <specific files>   # prefer specific files over git add -A
git commit -m "Add team share feature"
```

### Step 3 — Merge to main

```bash
git checkout main
git merge feature/your-feature-name
```

> **If there are merge conflicts:** Resolve them, then run `npm run typecheck` again to make sure nothing broke.

### Step 4 — Push to main

```bash
git push origin main
```

This triggers GitHub Actions automatically. The pipeline:
1. Runs `pytest` (backend tests)
2. Runs `npm run typecheck` + `npm run lint` (frontend checks)
3. Builds the Docker image → pushes to ECR
4. Builds frontend → uploads to S3 → invalidates CloudFront cache
5. SSM command to EC2 → pulls new Docker image → restarts containers
6. Runs `alembic upgrade head` inside the container

> **Watch the pipeline:** Go to your GitHub repo → Actions tab → watch the running workflow. It takes about 5-8 minutes. If any step fails, the deploy is aborted — production keeps running the old version.

### Step 5 — Verify in production

After the pipeline succeeds:

1. Hard-refresh `rkteambuilder.com` (Ctrl+Shift+R) to bypass browser cache
2. Test the new feature on the live site
3. Check for any errors in the backend logs:
   ```bash
   ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
   cd /home/ubuntu/rktb
   docker compose -f docker-compose.prod.yml logs -f backend
   ```

---

## Part 5: Common Feature Scenarios

### Updating monster stats / traits / game data

**Data-only changes (no new fields):**
```bash
# 1. Edit the raw data JSON files in backend/data/ directly
#    (monsters.json, moves.json, traits.json, monster_moves.json, etc.)

# 2. Run validation to catch issues before importing
source ~/.venvs/rktb310/bin/activate
python3 backend/scripts/validation/run_all_checks.py

# 3. Import into local DB to verify
python3 -m backend.scripts.maintenance.update_game_data

# 4. Test locally at http://localhost:5173
# 5. Push to main → CI deploys
# 6. After deploy, sync production DB:
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb
docker compose -f docker-compose.prod.yml exec backend python3 -m backend.scripts.maintenance.update_game_data
```

> **Note:** `update_game_data` uses safe upserts — it never drops tables or deletes user data. Use `reset_and_reimport` **only in local dev** when you need a clean slate (it drops all tables including user teams).

> **The importer does NOT run automatically on deploy** — you must trigger it manually on production every time game data changes. CI only handles code and migrations.

**Bulk stat/trait updates from Excel (`data_stats_traits_formal.xlsx`):**

The `update_stats_traits` pipeline reads the Excel source of truth and patches `monsters.json` and `traits.json` automatically.

```bash
source ~/.venvs/rktb310/bin/activate

# Optional: check type/trait consistency first
python3 -m backend.scripts.update_stats_traits.check_types_and_traits

# Preview changes without writing anything
python3 -m backend.scripts.update_stats_traits.apply_updates --dry-run

# Apply changes (writes monsters.json + traits.json, creates timestamped backups)
python3 -m backend.scripts.update_stats_traits.apply_updates

# Then validate + import as normal
python3 backend/scripts/validation/run_all_checks.py
python3 -m backend.scripts.maintenance.update_game_data
```

**If you wrote a new script to generate or update the raw data files:**
```bash
# 1. Write and run the script locally — it updates the raw data files directly
source ~/.venvs/rktb310/bin/activate
python3 -m backend.scripts.your_new_script

# 2. Validate and import locally to verify
python3 backend/scripts/validation/run_all_checks.py
python3 -m backend.scripts.maintenance.update_game_data

# 3. Test locally at http://localhost:5173
# 4. Push to main — commit both the script AND the updated data files
# 5. Sync production DB
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb
docker compose -f docker-compose.prod.yml exec backend python3 -m backend.scripts.maintenance.update_game_data
```

> **Why not run the script on production?** The script already updated the data files locally and you committed those files, so production gets the correct JSON via deploy. No need to re-run the script on EC2 — just run the importer.

**If new fields are needed (schema change):**
1. Update `backend/models.py` with new columns
2. Generate and apply migration locally:
   ```bash
   cd backend
   alembic revision --autogenerate -m "describe the change"
   alembic upgrade head
   ```
3. Update importer scripts to populate the new fields
4. Run `update_game_data` locally to verify
5. Push to main → CI runs migrations automatically on deploy, then trigger importer on production manually

> **Branch or not?** Use a branch if you're editing importer scripts or models. For raw data file updates only (no logic changes), pushing directly to main is fine.

---

### Frontend-only changes (UI, responsive design, styling)

No backend restart needed — just run the frontend:
```bash
git checkout -b feature/your-ui-change
cd frontend && npm run dev
```

For responsive/large screen changes, use Tailwind's `2xl:` prefix (1536px+) for overrides. Test in Chrome DevTools → responsive mode at 1440px, 1920px, 2560px.

```bash
# Checks before pushing
cd frontend && npm run typecheck && npm run lint

git checkout main
git merge feature/your-ui-change
git push origin main  # only frontend pipeline runs, ~2-3 min deploy
```

---

### Handling merge conflicts (when main has moved ahead)

If you've been working on a feature branch while other changes were pushed to main, sync before merging:

```bash
# On your feature branch — pull main's latest commits in
git pull origin main
```

If git reports conflicts, resolve them (VS Code has a built-in conflict UI), then:
```bash
git add <resolved files>
git commit
# Now merge to main as normal
git checkout main
git merge feature/your-feature
git push origin main
```

> **Rule of thumb:** Always run `git pull origin main` into your feature branch before merging back, especially if you've been on the branch for more than a day. The longer you wait, the messier conflicts get.

---

## Part 6: Data Scripts Reference

### Validation scripts (`backend/scripts/validation/`)

```bash
source ~/.venvs/rktb310/bin/activate

# Run all checks at once (recommended before any data import)
python3 backend/scripts/validation/run_all_checks.py

# Individual checks:
python3 backend/scripts/validation/check_local_consistency.py   # monsters.json vs other JSONs
python3 backend/scripts/validation/check_source_correctness.py  # JSON vs Excel source of truth
python3 backend/scripts/validation/check_frontend_images.py     # image files vs monsters/moves
python3 backend/scripts/validation/count_table_records.py       # DB row counts
```

### Stats/trait update pipeline (`backend/scripts/update_stats_traits/`)

Used to bulk-apply stat and trait updates from `data_stats_traits_formal.xlsx`:

```bash
# Check type/trait consistency between Excel and JSON
python3 -m backend.scripts.update_stats_traits.check_types_and_traits

# Preview stat/trait changes without writing files
python3 -m backend.scripts.update_stats_traits.apply_updates --dry-run

# Apply changes (patches monsters.json + traits.json, creates timestamped backups)
python3 -m backend.scripts.update_stats_traits.apply_updates

# Mark the Excel file with color-coded change indicators
python3 -m backend.scripts.update_stats_traits.mark_excel
```

### Video stats extraction (`backend/scripts/video_extract/`)

Extracts monster base stats from gameplay video using OCR:

```bash
# Place video.mp4 at project root, then:
python3 -m backend.scripts.video_extract.extract_monster_stats
# Output: stats_from_video.json (confirmed entries) + stats_review_queue.json (needs review)
```

### Other useful scripts

```bash
# Import name mapping changes back into moves.json / traits.json
python3 -m backend.scripts.name_management.apply_move_name_changes
python3 -m backend.scripts.name_management.apply_trait_name_changes

# Clean up expired guest accounts
python3 -m backend.scripts.cleanup_expired_guests
```

---

## Part 7: Optional Environment Variables

These are not required for basic local dev but are useful for tuning:

| Variable | Default | Description |
|---|---|---|
| `ENABLE_REFERENCE_RESOLUTION` | `true` | When true, filters LLM prompts to only include game terms (moves, traits, etc.) actually referenced by the team — reduces token count and improves analysis focus |
| `GEMINI_THINKING_BUDGET` | `24576` | Token budget for Gemini's thinking mode (512–24576). Higher = deeper reasoning, slower response |
| `DEEPSEEK_TIMEOUT` | `200.0` | HTTP timeout in seconds for DeepSeek API calls |
| `ANALYSIS_TEMPERATURE` | `0.7` | LLM sampling temperature for analysis |
| `ANALYSIS_MAX_TOKENS` | `32768` | Max output tokens per analysis response |
| `RETRY_GRACE_TTL` | `900` | Seconds a user can retry a failed analysis for free (default 15 min) |
| `RETRY_GRACE_MAX_RETRIES` | `3` | Max free retries within the grace window |

---

## Part 8: If Something Goes Wrong

### Option A — Revert via git (safest, re-runs CI)

```bash
git revert HEAD          # creates a new "undo" commit
git push origin main     # triggers full CI pipeline with old code
```

Takes ~8 minutes. Tests run, confirming the rollback is clean.

### Option B — Direct Docker rollback on EC2 (faster, ~2 min, backend only)

ECR images are tagged with the git commit SHA. Find the previous SHA from `git log`, then:

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb

# Pull the previous image
ECR="273130558025.dkr.ecr.ap-southeast-1.amazonaws.com/rktb-backend"
docker pull $ECR:<previous-commit-sha>

# Edit docker-compose.prod.yml: change image tag from :latest to :<previous-sha>
# Then restart backend only:
docker compose -f docker-compose.prod.yml up -d --no-deps backend
```

> **Note:** This only rolls back the backend. If the frontend also needs rolling back, use Option A.

### Checking production logs for errors

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb

# Live log stream
docker compose -f docker-compose.prod.yml logs -f backend

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail=100 backend
```

---

## Quick Reference Cheatsheet

```bash
# ── Start local environment ──────────────────────────────────
docker compose up -d redis
sudo service postgresql start
source ~/.venvs/rktb310/bin/activate
python3 -m uvicorn backend.main:app --reload --env-file backend/.env
# (new terminal)
cd frontend && npm run dev

# ── Daily dev workflow ───────────────────────────────────────
git checkout -b feature/my-feature    # new branch
# ... write code ...
cd backend && pytest -v               # backend tests
cd frontend && npm run typecheck      # TS check
cd frontend && npm run lint           # lint

# ── Game data update (local) ─────────────────────────────────
python3 backend/scripts/validation/run_all_checks.py     # validate first
python3 -m backend.scripts.maintenance.update_game_data  # import to local DB

# ── Deploy ───────────────────────────────────────────────────
git checkout main
git merge feature/my-feature
git push origin main                  # triggers auto-deploy
# Watch: GitHub → Actions tab

# ── Game data update (production, after deploy) ──────────────
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb
docker compose -f docker-compose.prod.yml exec backend python3 -m backend.scripts.maintenance.update_game_data

# ── Production logs ──────────────────────────────────────────
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
docker compose -f docker-compose.prod.yml logs -f backend
```
