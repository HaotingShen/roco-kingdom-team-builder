# Team Analysis System — Architecture, Behavior, and 2026-07-05 Review

**Status: CURRENT** — written 2026-07-05 after a full line-by-line review of the
analysis system (backend + frontend), the fixes applied during that review, and
end-to-end verification against a local Postgres/Redis/DeepSeek stack.
This document is the authoritative reference for how team analysis works.
The historical quota/auth details in `user-auth-system.md` remain accurate.

> **2026-07-06 update — the analysis code was extracted from `main.py` into the
> `backend/analysis/` package (behavior-preserving refactor; no API/DB/quota/
> cache/auth/response changes).** Where this doc says "in `main.py`" for an
> analysis function, it now lives in the package — see the module map in §0.
> The routes are registered via `app.include_router(analysis_router)` in
> `main.py` and keep the exact same paths, response models, and tags.

---

## 0. Module map (`backend/analysis/`)

| Module | Contents |
|---|---|
| `routes.py` | `APIRouter` with the 5 endpoints: `POST /team/analyze`, `POST /team/analyze_by_id`, `POST /analysis/save`, `GET /teams/{id}/analysis`, `DELETE /teams/{id}/analysis` |
| `service.py` | `_perform_team_analysis` — the core engine (data load, 7 prompts, concurrent cached LLM calls, error classification, result assembly) |
| `quota.py` | `_AnalysisQuotaContext`, `_resolve_analysis_effective_user`, `_analysis_quota_preflight`, `_analysis_quota_postflight` |
| `cache_keys.py` | `generate_monster_cache_key`, `compute_willpower_categories`, `generate_team_cache_key`, `_load_willpower_categories_if_needed`, `generate_team_composition_hash`, `check_if_all_cached` |
| `prompts.py` | `BATTLE_MECHANICS_ZH/EN`, `build_trait_synergy_prompt`, `build_team_synergy_prompt` |
| `computations.py` | `compute_effective_stats`, `compute_energy_profile`, `resolve_dynamic_move_properties`, `compute_counter_coverage`, `compute_defense_status_move`, `compute_type_coverage`, `compute_magic_item_eval`, `generate_recommendations` |
| `localization.py` | `get_localized_name` / `_description` / `_move_category` |
| `persistence.py` | `save_or_update_analysis` |

Import direction (acyclic): `routes → service/quota/persistence → prompts/cache_keys → computations → localization`. The shared `redis_cache` singleton lives in `backend/cache.py` (imported by both the package and `main.py`). Analysis Pydantic schemas remain in `backend/schemas.py`. `update_team`'s stale-analysis deletion stays in `main.py` (it's a Teams route, not an analysis route). `main.py` re-exports `compute_effective_stats`, `compute_type_coverage`, `generate_team_cache_key`, `generate_team_composition_hash`, and `_perform_team_analysis` for the test suite.

## 1. End-to-end flow

### Entry points

| Trigger | Endpoint | Used by |
|---|---|---|
| "Analyze" in the builder | `POST /team/analyze` (inline `TeamCreate` payload) | `BuilderPage.tsx` — always, even for a loaded saved team |
| "Analyze" on a saved team page | `POST /team/analyze_by_id` | `SavedTeamPage.tsx` |

Both endpoints use `get_user_or_anonymous` and resolve an **effective user**:
an anonymous request whose `device_id` cookie maps to an existing account uses
that account's quota (prevents log-out-for-fresh-quota).

### Pipeline (shared by both endpoints)

1. **Pre-flight** (`_analysis_quota_preflight`, `analysis/quota.py` — deduplicated
   from ~200 lines per endpoint in the 2026-07-05 fix pass):
   - `team_hash` = language-independent md5 of composition (magic item, monsters,
     legacy types, moves — NOT personality/talent/name).
   - `check_if_all_cached()` — are all 7 `llm_cache:*` Redis keys present?
   - **Cached path**: retry-grace check → `user_analyzed:*` already-paid check →
     per-user quota check → atomic slot claim (`SET NX EX`). No device/IP caps,
     no rate limits (no LLM cost to protect).
   - **Non-cached path**: circuit breaker (503, no charge) → grace check →
     per-user quota check → device daily cap → IP cap (only when device unknown;
     deliberate — CGNAT) → per-team 60s rate key → **in-flight concurrency cap
     (max 2 per identity, added 2026-07-05)** → record rate key → consume grace.
2. **`_perform_team_analysis`**: loads all game data, builds 6 per-monster
   trait-synergy prompts + 1 team-synergy prompt, resolves game-term references,
   **closes the DB session**, then `asyncio.gather`s 7 LLM calls through
   `RedisCache.get_or_compute` (distributed lock + keep-alive, 1h TTL; failures
   never cached). Errors are classified: auth → 401, all-quota → 429, transient →
   per-slot error markers + `has_partial_errors=true`. Local computations
   (effective stats, energy, counters, type coverage, magic item eval,
   recommendations) are added server-side.
3. **Post-flight** (`_analysis_quota_postflight`): total failure → clear rate key
   (instant retry allowed). Charge quota **only** when `actual_llm_calls > 0 and
   successful_calls > 0`; partial success additionally grants **retry grace**
   (3 free retries / 15 min). Cached path charges only the request that claimed
   the slot.
4. **Server-side auto-save (`analyze_by_id` only, added 2026-07-05)**: when the
   requester owns the team, the team is not featured, and the analysis fully
   succeeded, the result is persisted to `team_analyses` — this is what makes an
   analysis of a saved team appear on the owner's other devices with no manual
   step. Partial results are never persisted.

### The CloudFront 120s timeout dance (load-bearing, do not break)

- CloudFront returns 504 at 120s while the backend keeps computing.
- The frontend retries the **analyze mutations only, once, on 5xx/network error**
  (`analyzeMutationRetry` in `lib/constants.ts`).
- The per-team rate key has TTL 60s (< 120s), so the retry passes rate limiting,
  blocks on the LLM-cache distributed lock, and returns the original run's
  result with `actual_llm_calls == 0` → **no second quota charge**.
- The new in-flight cap is 2 (not 1) precisely so this retry is never rejected.

### Persistence & cross-device sync

- `team_analyses` table: one row per `(team_id, language)` (unique constraint),
  JSONB `analysis_data`, `is_from_cache`, `created_at`.
- Endpoints: `POST /analysis/save` (owner), `GET /teams/{id}/analysis` (owner;
  **falls back to the other language** when the requested one has no row —
  added 2026-07-05), `DELETE /teams/{id}/analysis` (owner).
- Saves happen three ways:
  1. **Backend auto-save** after successful `analyze_by_id` (new).
  2. **Frontend auto-save** after a successful builder analyze when the payload
     matched the saved team at click time (`teamId` set, not dirty, not
     featured, logged in) (new).
  3. Manual "Save Analysis" button (unchanged; still needed for a dirty/unsaved
     team after saving it).
- **Editing a team's composition deletes its saved analyses** (backend, in
  `update_team`) — a saved analysis can no longer describe a team it doesn't
  match. Name-only edits keep them. The frontend invalidates
  `["savedAnalysis", teamId]` after updates.
- The in-builder analysis result lives in the zustand `builderStore` and is
  **deliberately not persisted** to localStorage (as are `teamId` and
  `isAnalyzing`) — a refresh drops them. Recovery paths: saved teams reload the
  server-saved analysis; an unchanged team re-analyzed within the 1h cache TTL
  is free (`user_analyzed:*` marker).

### Frontend state map

- `builderStore` (persisted: name/magic item/slots only) — the draft.
- `analysisStore` (not persisted) — per-slot analysis-page state; **reset when a
  different team is loaded** (fix 2026-07-05).
- TanStack Query keys: `QUERY_KEYS.TEAM_DETAIL(id)` = `["teams", id]` (unified
  2026-07-05; SavedTeamPage previously used a private `["team", id]` key),
  `QUERY_KEYS.SAVED_ANALYSIS(id, lang)` = `["savedAnalysis", id, lang]`,
  `QUERY_KEYS.QUOTA` (+userId).
- Auth transitions (login / continue-as-guest / password change) clear the query
  cache and the builder's team reference (fix 2026-07-05; logout already did).

---

## 2. Bugs found and FIXED in the 2026-07-05 review

### Security / correctness (backend)
1. **IDOR — `/team/analyze_by_id` had no ownership check.** Anyone (even
   anonymous) could analyze any team by sequential integer ID and receive its
   full composition. Now: owner (direct auth or device-linked account) or
   featured teams only; 403 otherwise. Regression-tested.
2. **`/teams/featured` leaked the owner's `UserOut`** (email, tier, timestamps)
   to unauthenticated callers, and cached the leak in Redis. Owner now redacted.
3. **`TeamUpdate` bypassed create-path validation** — no 6-monster bound, no
   talent rules (`TalentUpsert` now inherits `TalentIn`'s validator;
   `user_monsters` now `min/max_length=6`). A crafted PUT could store a team
   that made `analyze_by_id` 500 or inflated LLM cost.
4. **Willpower Enhancement cache-key bug** — the team prompt states whether each
   monster's Willpower Impact becomes Physical or Magic (depends on
   personality + talent), but the team cache key ignored those inputs, so two
   different builds could share one cached (wrong) team analysis. The key now
   includes a per-monster P/M signature for ENHANCE_SPELL teams. Also,
   "Willpower Impact" is now rejected as a *selected* move (400) — it's granted
   in battle by the magic item, is in no move pool, and its dynamic resolution
   isn't encoded in the per-monster cache key.
5. **`compute_effective_stats` float rounding** — half-up rounding was applied to
   float artifacts (e.g. exact 235.5 computed as 235.4999…), giving off-by-one
   stats at boundary values. Now exact `Decimal` end-to-end. Regression-tested.
6. **`save_or_update_analysis`** — SELECT-then-INSERT race on the
   `(team_id, language)` unique constraint 500'd one of two concurrent saves
   (now retried as update); also wrote a naive `datetime.utcnow()` into a
   tz-aware column (now `datetime.now(timezone.utc)`); `/analysis/save` now
   stores `model_dump(mode="json")`.
7. **Stale saved analysis after team edit** — `update_team` now deletes the
   team's saved analyses when the composition (monsters/moves/legacy/
   personality/talent/magic item) changes.
8. **LLM malformed-JSON output** (observed live with deepseek-v4-flash thinking
   mode): a single bad JSON payload failed one of 7 calls → partial result,
   quota charged, grace burned. `generate_analysis_json` now retries the call
   once on `JSONDecodeError`. (Verified live: the retry fired and rescued a run.)
9. **Quota TOCTOU (bounded, not eliminated)** — per-user quota is checked at
   start but charged after the ~60s run, so a parallel burst of different-team
   requests could exceed the daily limit. New per-identity in-flight cap
   (max 2 concurrent non-cached analyses) bounds the overshoot while keeping
   the CloudFront retry alive. See §4 for the residual.
10. **Expired-token identity downgrade** — `get_user_or_anonymous` silently
    treated any invalid/expired Bearer token as anonymous. Consequences: the
    quota display showed anonymous numbers to logged-in users after the 15-min
    token expiry (200-with-wrong-data, so the axios refresh interceptor never
    fired), and locked accounts kept anonymous quota. Now: a presented-but-bad
    token raises 401/403, which the frontend interceptor recovers from by
    refreshing. No-token requests are anonymous as before.
11. **FK-violation 500s** — bad IDs in create/update team now return 400;
    concurrent first-visit guest creation races now adopt the winning row
    instead of 500ing; `analyze_by_id` on a malformed stored team returns 400
    ("team is incomplete") instead of 500.
12. **CORS default** was `"*"` with `allow_credentials=True` (any site could
    make credentialed requests if `ALLOWED_ORIGINS` were ever unset). Default
    is now localhost dev origins. Production explicitly sets the var (compose).
13. Cosmetics/consistency: `AttackStyle.PHYSICAL` enum repr leaked into
    recommendation text (now localized value); dev-only `reset-users` skipped
    guests due to SQL NULL semantics; dead code removed (unused slowapi
    `analysis_rate_limit` decorator/`_apply_rate_limit_check`, frontend
    `forceRefresh`/`getQuotaStatus` endpoints that pointed at nonexistent routes).

### Frontend
14. **Global mutation retry** re-POSTed *every* mutation once on 5xx/network
    error — e.g. a 502 after `createTeam` committed created a duplicate team.
    Now no global retry; only the two analyze mutations opt in (the CF-timeout
    recovery, which the backend dedupes).
15. **Failed re-analyze destroyed the previous result** (cleared up-front). The
    previous analysis is now snapshotted and restored on error; quota display
    also refreshes on error (a timed-out run may still have charged).
16. **Cross-language invisibility** — an analysis saved under `zh` looked
    "never saved" on an `en`-defaulting device (fetch was language-keyed,
    404 + no retry). Backend GET now falls back to the other language.
17. **State leaks across identities/teams**: login/guest-login/password-change
    now clear the query cache and builder team reference (logout already did);
    deleting a team clears a matching builder `teamId` (Update no longer PUTs a
    404); `loadFromTeam` resets `isFeaturedTeam` (stale flag pointed the Update
    button at the admin featured-team API) and resets per-slot analysis-page
    state when a different team loads.
18. **Hardening**: `analysesMatch` no longer crashes the page on legacy/partial
    stored `analysis_data`; the two analyze calls have a 5-minute axios timeout
    so a hung connection can't wedge the global `isAnalyzing` flag until refresh.

---

## 3. Verified behavior (2026-07-05, local E2E against Postgres+Redis+DeepSeek)

- Guest creation, quota display (guest 0/2 → 1/2 → 2/2 tracked correctly).
- `GET /auth/quota` with garbage Bearer → 401 (interceptor recovery path).
- Team create → analyze (owner) → **full 7-call DeepSeek analysis, one
  malformed-JSON retry fired and rescued the run** → `has_partial_errors=false`.
- **Auto-save**: saved analysis deleted beforehand, present (200) right after
  analyze; re-analyze updated it with `is_from_cache=true`.
- Cached re-analyze: 0.078s, quota unchanged.
- Language fallback: `?language=zh` returned the `en` row with `language: "en"`.
- Ownership: anonymous → 403; other guest → 403; unknown team → 404.
- Composition edit → saved analysis deleted (404); name-only edit → kept (200).
- PUT with 3 monsters → 422; Willpower Impact as selected move → 400.
- Partial-failure path (Gemini free-tier 429s): error markers, NO quota charge,
  NO bad cache entries, per-team rate key cleared for instant retry.
- Full backend suite: 178 passed (includes new `tests/test_analysis_fixes.py`;
  conftest now emulates `timezone()/now()` on SQLite so endpoint-level auth
  tests actually run). Frontend: typecheck, lint (0 errors), production build.

---

## 4. Known limitations / residual risks (documented decisions, not bugs)

- **Quota check-then-charge race remains, bounded**: with the in-flight cap of
  2, a determined user can overshoot their daily limit by at most ~1 per burst.
  Charging up-front with refunds was rejected: it would 429 the CloudFront
  retry at the quota edge and charge users when the daily 21:00 UTC backend
  restart kills in-flight runs.
- **No per-IP throughput limit on analyze endpoints** — deliberate (commit
  6b7d910): CGNAT'd Chinese mobile users share IPs; the IP daily cap only
  applies when the device cookie is missing. The `tier:ip:*:daily` counter is
  written but effectively never read for browsers.
- **Logout doesn't kill the current access token** (≤15 min residual validity;
  refresh token IS revoked). Documented tradeoff; `/auth/logout-all` bumps
  `token_version` for a hard kill. Refresh tokens are not rotated on use.
- **`/auth/quota` shows the device-linked account's tier/usage to an
  unauthenticated caller on the same device** — required for the honest quota
  display after logout; team counts are redacted.
- **Anonymous users cannot persist analyses** (no team ownership) — their
  results live only in memory + the 1h LLM cache.
- **`/analysis/save` stores client-supplied content** (owner-only read, shape
  validated). The `analyze_by_id` auto-save is server-authoritative; the
  builder-path save is not.
- **CAPTCHA fails open** on provider outage/misconfig (documented choice).
- **Email normalization**: registration stores RFC-normalized email; login/reset
  lookups use raw `.lower()`. Only matters for IDN emails; left as is.
- **Teams-limit and guest-creation check-then-act races** can overshoot by 1 on
  concurrent requests (cheap resources; not worth locking).
- UTC day boundaries: daily quotas reset at 08:00 Beijing time.

## 5. Test/verify checklist for future analysis changes

1. `cd backend && pytest -v` (SQLite; `test_analysis_fixes.py` covers ownership,
   update validation, rounding boundaries, willpower keys, strict 401).
2. `docker compose up db redis -d` + seed via `reset_and_reimport` (LOCAL ONLY),
   boot uvicorn with overridden `DATABASE_URL`/`REDIS_URL`, and drive:
   guest → create team → analyze_by_id → saved analysis GET → edit team →
   saved analysis 404. (See §3 for expected outcomes.)
3. Never break: the CF-timeout retry contract (§1), grace lifecycle, and the
   `actual_llm_calls == 0 → no charge` rule.
