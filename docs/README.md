# Documentation

Reference docs for Roco Kingdom Team Builder. Everything here is prose — the
authoritative source for behaviour is always the code.

## How the system works

| Doc | Covers |
|---|---|
| [analysis-system.md](analysis-system.md) | Team-analysis flow end to end: quota, caching, the 7 LLM calls, persistence. Module map in §0. Authoritative for anything analysis-related. |
| [user-auth-system.md](user-auth-system.md) | JWT access/refresh, guest accounts, device tracking, tiers, anti-abuse. |
| [team-share-implementation.md](team-share-implementation.md) | Stateless share-link encoding and the import flow. |
| [bilingual-url-locale-refactor.md](bilingual-url-locale-refactor.md) | `/en/` + `/zh/` path routing, hreflang/canonical, the CloudFront locale function. |

## Running it in production

| Doc | Covers |
|---|---|
| [deployment-complete.md](deployment-complete.md) | Full AWS architecture — EC2, RDS, S3, CloudFront, Parameter Store. Start here. |
| [ops-guide.md](ops-guide.md) | Day-to-day operational commands and runbooks. |
| [rds-az-migration-runbook.md](rds-az-migration-runbook.md) | The 2026-04 RDS availability-zone move. |
| [umami-setup.md](umami-setup.md) | Self-hosted analytics setup. |

## Working on it

| Doc | Covers |
|---|---|
| [local-dev.md](local-dev.md) | Local environment setup. |
| [testing-guide.md](testing-guide.md) | Test suite layout and which tests need a live Postgres. |

## Completed projects

Kept for context on why things are the way they are.

| Doc | Covers |
|---|---|
| [deepseek-v4-migration-plan.md](deepseek-v4-migration-plan.md) | Move off the retired `deepseek-reasoner` (done 2026-06). |
| [spa-routing-seo-fix.md](spa-routing-seo-fix.md) | SPA deep-link and SEO fixes. |
| [taptap-integration.md](taptap-integration.md) | TapTap static build and submission. |
| [notes.txt](notes.txt) | Loose working notes. |

---

**Not in this folder:** `README.md` and `LICENSE` stay at the repository root, where
GitHub expects them. `CLAUDE.md` is untracked and local-only.

Some operational runbooks are deliberately kept **out of version control** because they
contain real traffic and usage figures and this repository is public. If a doc is
referenced but missing, that is why.
