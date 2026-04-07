# Roco Kingdom Team Builder

> A production full-stack web app for building and analyzing PvP teams in the mobile game **Roco Kingdom: World**.
> Live at **[rkteambuilder.com](https://rkteambuilder.com)**

---

## What It Does

Players configure a 6-monster team — choosing personality, moves, legacy type, and talent allocation per monster — then run an AI-powered analysis that evaluates:

- **Trait-move synergies** per monster (via LLM)
- **Type coverage** and team-wide defensive weaknesses
- **Energy economy**, counter triangle balance, and role diversity
- **Magic item** compatibility and best-target recommendation

Results are cached in Redis and persisted to the database, so re-viewing is instant and free.

---

## Technical Highlights

**LLM Integration**
- 7 concurrent LLM calls per analysis (6 per-monster + 1 team-wide) using `asyncio.gather`
- Redis response cache (1-hour TTL) deduplicates identical requests across users
- Retry grace system: partial failures don't consume user quota

**Auth & Multi-Tier User System**
- Guest accounts auto-created on first visit via `device_id` cookie — zero friction onboarding
- Seamless guest → registered upgrade with full data migration
- JWT access tokens (15 min) + refresh tokens (7 days) in `httpOnly` cookies
- Cross-account abuse prevention: per-device and per-IP daily caps tracked in Redis

**Production Infrastructure**
- Dockerized backend deployed on AWS EC2, frontend on S3 + CloudFront
- All secrets managed through AWS Parameter Store
- GitHub Actions CI/CD: push to `main` → build Docker image → push to ECR → EC2 auto-restarts
- CloudWatch log integration for monitoring and daily digest alerts

**Other**
- Full bilingual UI (English / Chinese) with per-entity JSONB localization in PostgreSQL
- Game data stat formula implemented from scratch based on reverse-engineered game mechanics

---

## Stack

| | |
|---|---|
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS, TanStack Query |
| **Backend** | Python, FastAPI, SQLAlchemy 2.x, Alembic |
| **Database** | PostgreSQL (AWS RDS) |
| **Cache** | Redis |
| **LLM** | Gemini (local dev) / DeepSeek (production) |
| **Infra** | AWS EC2, S3, CloudFront, ECR, Parameter Store |

---

## Architecture

```
Browser → CloudFront
  │
  ├── /* ───────────────────> S3                 (React SPA)
  │
  └── /api/* ───────────────> EC2 (Docker)
                                  ├── FastAPI   ← uvicorn, 2 workers
                                  ├── Redis     ← LLM cache + quota counters
                                  └── Umami     ← self-hosted analytics
                                  │
                              RDS PostgreSQL
                                  ├── roco_kingdom  (app data)
                                  └── umami         (analytics data)
```

---

## Local Setup

**1. Clone and install dependencies**
```bash
git clone https://github.com/HaotingShen/roco-kingdom-team-builder.git
cd roco-kingdom-team-builder

# Backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

**2. Start PostgreSQL and Redis**

The easiest way is via the included Docker Compose file:
```bash
docker compose up db redis -d
```
This spins up PostgreSQL 16 (port 5432) and Redis 7 (port 6379) locally. Alternatively, install and run them manually.

**3. Configure environment**

Create `backend/.env`:
```bash
DATABASE_URL=postgresql+psycopg2://rktb_admin:localdev@localhost/roco_kingdom
SECRET_KEY=<any-random-32+-character-string>
LLM_PROVIDER=gemini              # gemini for local dev
GEMINI_API_KEY=...               # get from aistudio.google.com
REDIS_URL=redis://localhost:6379/0
FRONTEND_URL=http://localhost:5173
```

**4. Run database migrations and import game data**
```bash
# Run from backend/ directory
cd backend && alembic upgrade head && cd ..

# Run from project root — imports all game data (monsters, moves, types, etc.)
python3 -m backend.scripts.importers.reset_and_reimport
```

> `reset_and_reimport` drops and recreates all tables. **Local development only** — never run on production.

**5. Start the servers**
```bash
# Backend — API at http://localhost:8000, interactive docs at http://localhost:8000/docs
python3 -m uvicorn backend.main:app --reload --env-file backend/.env

# Frontend — in a separate terminal
cd frontend && npm run dev
# App at http://localhost:5173
```

---

## Contributing

**Branch and PR workflow**
```bash
# Always branch off main
git checkout main && git pull origin main
git checkout -b feature/your-feature-name

# After making changes
git add <specific files>
git commit -m "Short description of change"
git push origin feature/your-feature-name
# Then open a PR on GitHub targeting main
```

**Guidelines**
- Open an issue first to describe the feature before writing code
- Keep PRs focused — one feature or fix per PR
- New features should live in `frontend/src/features/<feature-name>/` as self-contained modules
- Avoid modifying existing pages or backend endpoints unless discussed first

---

## Tests

```bash
cd backend && pytest -v
```

Covers auth flows, stat formula correctness, game term extraction, username validation, and retry grace logic.
