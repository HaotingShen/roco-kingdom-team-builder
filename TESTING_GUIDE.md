# Testing Guide — Quota & Auth System

## Tier Limits Reference

| Tier | Daily Analyses | Monthly Analyses | Team Slots |
|------|---------------|-----------------|------------|
| Anonymous | 1 | 5 | 0 |
| Guest | 2 | 30 | 3 |
| Free (registered) | 5 | 100 | 100 |
| Premium | 20 | 500 | 500 |
| Unlimited | ∞ | ∞ | ∞ |

**Cross-account device daily cap:** 5 non-cached (real LLM) analyses per device per day, across all accounts.
Cached results skip this cap entirely.

**Quota inheritance (seeding):** When a new guest or registered account is created, the backend seeds its daily counter from the device's cross-account cap count. This means prior anonymous or cross-account usage on the same device shows up immediately in the new account's quota display.

**Cache TTL:** LLM results cached ~1 hour. `user_analyzed` marker (tracks who already paid for a team) TTL: 1 hour.

**Guest creation limit:** 2 per IP per day.

---

## Reset Between Tests

### Full reset (fresh state, same device):
```bash
# DB: delete all non-system users and teams
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192

DB_URL=$(aws ssm get-parameter --name /rktb/prod/DATABASE_URL --with-decryption --query Parameter.Value --output text --region ap-southeast-1)
psql "${DB_URL/postgresql+psycopg2/postgresql}" -c "
DELETE FROM teams WHERE owner_id IN (SELECT id FROM users WHERE is_system = FALSE);
DELETE FROM users WHERE is_system = FALSE;
TRUNCATE deleted_emails;
"


# Redis: clear all quota/rate/cache keys (preserves JWT blacklist)
EVAL "local k=redis.call('keys','tier:*'); if #k>0 then return redis.call('del',unpack(k)) else return 0 end" 0
EVAL "local k=redis.call('keys','LIMITS:LIMITER/*'); if #k>0 then return redis.call('del',unpack(k)) else return 0 end" 0
EVAL "local k=redis.call('keys','retry_grace:*'); if #k>0 then return redis.call('del',unpack(k)) else return 0 end" 0
EVAL "local k=redis.call('keys','llm_cache:*'); if #k>0 then return redis.call('del',unpack(k)) else return 0 end" 0
EVAL "local k=redis.call('keys','user_analyzed:*'); if #k>0 then return redis.call('del',unpack(k)) else return 0 end" 0
```

To simulate a truly fresh device (brand new visitor), also clear the `device_id` cookie in the browser DevTools. You should log out before clearing the device_id cookie — logout invalidates the refresh token, then clearing device_id gives you a genuinely fresh anonymous visitor with no ties to any prior account.

### Preserve LLM cache (for cached-path tests):
Run all Redis commands above **except** the `llm_cache:*` line.

---

## Section 1 — Anonymous User

### 1-A. Basic quota enforcement
**Steps:** Open the site without any account. Analyze any team (non-cached).
**Expected:** Count shows 1/1. Quota charged.

**Steps:** Analyze a second different team.
**Expected:** 429 error — daily limit reached.

---

### 1-B. Same team re-analysis within cache TTL
**Steps:** Analyze team X (1/1). Click Analyze on the same team again within ~1 hour.
**Expected:** Instant result. Count stays at 1/1. No double charge.

---

### 1-C. Anonymous cannot save teams
**Steps:** Build a team. Click Save.
**Expected:** Prompted to log in or create a guest account. Save is blocked.

---

## Section 2 — Guest User

### 2-A. Basic quota enforcement
**Setup:** Full reset. Create a guest account (starts at 0/2).
**Steps:** Analyze team X → 1/2. Analyze team Y → 2/2. Analyze team Z.
**Expected:** Third analysis returns 429.

---

### 2-B. Guest team save limit
**Steps:** Save 3 different teams. Try to save a 4th.
**Expected:** 4th save blocked with team limit error.

---

### 2-C. Guest re-analysis of own team within cache TTL
**Setup:** Guest at 1/2 (analyzed team X).
**Steps:** Click Analyze on team X again within ~1 hour.
**Expected:** Instant result. Count stays at 1/2.

---

### 2-D. Guest at daily limit re-accesses own cached team
**Setup:** Guest at 2/2. Team X (previously analyzed by this guest) still cached.
**Steps:** Click Analyze on team X.
**Expected:** Instant result. Count stays at 2/2. No 429.

---

### 2-E. Guest creation rate limit
**Setup:** Full reset. On the same IP: create and clear guest data twice (consuming both daily guest creations).
**Steps:** Try to create a third guest account on the same day.
**Expected:** 429 — guest creation limit reached for this IP today.

---

## Section 3 — Free (Registered) User

### 3-A. Basic daily quota enforcement
**Setup:** Full reset. Register a new account.
**Steps:** Analyze 5 different teams one by one.
**Expected:** Count increments 1/5 → 2/5 → 3/5 → 4/5 → 5/5.

**Steps:** Attempt a 6th analysis.
**Expected:** 429 — daily limit reached.

---

### 3-B. Re-analysis at limit (own cached team)
**Setup:** Registered user at 5/5. Team X was analyzed within the past hour (cached).
**Steps:** Click Analyze on team X.
**Expected:** Instant result. Count stays at 5/5. No 429.

---

### 3-C. Save and view teams
**Steps:** Build a team, save it. Open Teams page.
**Expected:** Team appears in list. Clicking it shows full details.

---

## Section 4 — Cross-User Quota (Cached Results)

**Important:** These tests require preserving `llm_cache` between users. Do NOT clear `llm_cache:*` after User A analyzes.

### 4-A. User B pays quota for User A's cached result
**Setup:** Full reset including `user_analyzed:*`. After User A analyzes, do NOT clear `llm_cache:*`.
**Steps:**
1. Register User A. Analyze team X. (User A: 1/5)
2. Log out. Register User B (different email).
3. User B builds the exact same team composition as X. Clicks Analyze.
**Expected:** Instant result (from cache). User B: 1/5. Quota charged.

---

### 4-B. User B re-analyzes same cached team (within TTL)
**Continuing from 4-A:**
**Steps:** User B clicks Analyze on team X again (within ~1 hour).
**Expected:** Instant result. User B stays at 1/5. No double charge.

---

### 4-C. User B at daily limit re-accesses their own cached result
**Setup:** User B is at 5/5. Team X (which User B analyzed before) is still cached.
**Steps:** User B clicks Analyze on team X.
**Expected:** Instant result. Count stays at 5/5. No 429.

---

### 4-D. Anonymous user gets instant result from registered user's cache
**Setup:** Registered user analyzed team X (cached). Clear `tier:*` and `user_analyzed:*` only (keep `llm_cache:*`). Log out → anonymous.
**Steps:** Anonymous user builds same team X, analyzes.
**Expected:** Instant result. Anonymous count: 1/1. Quota charged.

---

### 4-E. Multiple different users each pay independently
**Setup:** Full reset. Three users A, B, C each have fresh quota.
**Steps:**
1. User A analyzes team X (1/5, LLM runs).
2. User B analyzes same team X (1/5, instant cached, quota charged).
3. User C analyzes same team X (1/5, instant cached, quota charged).
**Expected:** Each user independently goes from 0 to 1. No free rides for B or C.

---

## Section 5 — Identity Transitions (Quota Inheritance)

Inheritance mechanism: when a new guest or registered account is created on a device, the daily counter is **seeded** from the device's cross-account cap count (total analyses done on that device today across all accounts). This keeps the quota display honest — prior usage on the device carries over.

### 5-A. Anonymous → creates guest, re-analyzes same cached team
**Setup:** Full reset. Anonymous user analyzes team X → count: 1/1. Do NOT clear `llm_cache:*`.
**Steps:** Create a guest account on the same device. Open team X. Click Analyze.
**Expected:**
- After account creation: guest count shows **1/2** (inherited from prior anonymous analysis on device).
- Team X analysis: instant result. Count stays at **1/2** (already paid as anonymous on same device — not re-charged).

---

### 5-B. Anonymous (at limit) → creates guest → analyzes new team
**Setup:** Anonymous user at 1/1.
**Steps:** Create a guest account. Build a different team Y (not previously cached). Click Analyze.
**Expected:**
- After account creation: guest count shows **1/2** (inherited).
- Analyzing team Y: LLM runs. Count: **2/2**.

---

### 5-C. Guest converts to registered (same account, keeps user_id)
**Setup:** Guest user has analyzed team X (1/2). Do NOT clear `llm_cache:*`.
**Steps:** Register email on the guest account (upgrade, same user_id). Analyze team X.
**Expected:** Instant result. Registered count stays at **1/5** (inherited from guest: same user_id, same Redis marker for team X).

---

### 5-D. Registered user deletes account → anonymous on same device
**Setup:** Registered user analyzes team X (1/5). Do NOT clear anything.
**Steps:** Delete account. Refresh. As anonymous user, view team X, analyze.
**Expected:**
- Anonymous count: **1/1** (inherited from the prior registered account's device usage).
- Result is instant (still cached). No 429 from device caps (cached results skip device cap check).

---

### 5-E. Guest (at limit) clears data → back to anonymous on same device
**Setup:** Guest at 2/2 (analyzed 2 teams). Clear guest data.
**Steps:** View quota as anonymous user on the same device.
**Expected:** Anonymous quota shows **1/1** (display shows at-limit; internally the device has used 2 analyses, but anonymous limit is 1/1 so it's capped at 1/1 in the display).

---

### 5-F. Registered user (at 5/5) deletes account → anonymous → cached team
**Setup:** Registered user analyzes 5 different teams (5/5), one of which is team X. Do NOT clear anything.
**Steps:** Delete account. Refresh. Build team X. Analyze.
**Expected:** Instant result. No 429 from device caps (cached results skip device cap check). Anonymous quota shows at-limit (1/1 inherited). The cached team is still accessible.

---

## Section 6 — Account Lifecycle

### 6-A. Delete account clears frontend query cache immediately
**Setup:** Registered user has 6 teams saved. Navigate to Teams page (teams are visible).
**Steps:** Go to Settings → Delete Account → confirm deletion.
**Expected:** Immediately after redirect to `/`, navigating to Teams page shows 0 teams. No stale team data visible. No need to refresh.

---

### 6-B. Clear guest data clears frontend query cache
**Setup:** Guest user has 3 teams saved. Teams page shows them.
**Steps:** Click "Clear Guest Data" in user menu → confirm.
**Expected:** After clearing, Teams page shows 0 teams immediately. User is anonymous.

---

### 6-C. Logout clears frontend query cache
**Setup:** Registered user has teams saved.
**Steps:** Click Logout.
**Expected:** Teams page shows 0 teams immediately after logout. No stale data.

---

### 6-D. Guest re-creation after clearing guest data
**Setup:** Create a guest account. Clear guest data.
**Steps:** Click "Continue as Guest" again.
**Expected:** New guest account created successfully. Count: 0/2 (or seeded from device if prior analyses existed). Old teams not visible.

---

### 6-E. Guest re-creation after account conversion (no 500 error)
**Setup:** Guest account exists on device. Register an email (converts the guest account to registered). Log out. Delete the registered account.
**Steps:** On the original device, click "Continue as Guest".
**Expected:** New guest account created successfully. No 500 error (stale soft-deleted guest record is cleaned up before re-creation).

---

## Section 7 — Device Daily Cap (Non-Cached Analyses Only)

The device daily cap (default: 5) prevents multi-account LLM abuse. It applies **only to real LLM calls**, not cached results. Premium/unlimited users are exempt.

### 7-A. Device daily cap blocks new non-cached analyses
**Setup:** Full reset. Same device. 5 different users each analyze 1 unique team (5 real LLM calls total on this device).
**Steps:** A 6th user on the same device tries to analyze a brand-new team (not cached).
**Expected:** 429 — device daily cap reached.

---

### 7-B. Device daily cap does NOT block cached results
**Continuing from 7-A (device cap at 5):**
**Steps:** That 6th user analyzes a team that is already cached (analyzed by one of the earlier users).
**Expected:** Instant result. Quota charged from the 6th user's own per-user limit. No 429 from device cap.

---

## Section 8 — Edge Cases

### 8-A. Concurrent same-user requests to same cached team
**Setup:** User has 1/5 remaining (4/5 used). Team X is cached.
**Steps:** Click Analyze twice rapidly (simulate double-click or open two tabs and analyze simultaneously).
**Expected:** Both requests return the result. Quota increments by 1 only (to 5/5), not 2. The second concurrent request gets the result for free (slot already atomically claimed by the first).

---

### 8-B. Viewing a saved team's stored analysis (no re-analysis)
**Setup:** Registered user previously analyzed and saved a team.
**Steps:** Navigate to Teams page → click the team → view the detail page.
**Expected:** Analysis results display immediately (loaded from DB). No LLM call. Quota unchanged.

---

### 8-C. Re-analysis of saved team via Teams page
**Setup:** Registered user has a saved team with stored analysis. Team is also cached in Redis.
**Steps:** On the saved team's detail page, click Analyze again.
**Expected:** Instant result (cached). If within the same TTL window as the original analysis, quota unchanged. If TTL expired (new LLM call), quota increments.

---

### 8-D. Anonymous user tries to analyze a team at the anonymous daily limit, then creates a guest account and analyzes a different non-cached team
This is a combination of 5-B to confirm the full flow end-to-end.
**Steps:**
1. Anonymous: analyze team X → 1/1 (at limit).
2. Anonymous: try to analyze team Y → 429.
3. Create guest account → count shows 1/2 (inherited).
4. Guest: analyze team Y (non-cached) → LLM runs → count: 2/2.
5. Guest: try to analyze team Z (non-cached) → 429.
**Expected:** Each step produces the outcome listed above.

---

## Section 9 — Redis State Verification (Advanced)

After running tests, verify Redis keys directly:

```bash
# Anonymous device quota
redis-cli KEYS "tier:anon:device:*"
redis-cli GET "tier:anon:device:{device_id}:daily:{YYYY-MM-DD}"

# Per-user quota (guest or registered)
redis-cli KEYS "tier:user:*"
redis-cli GET "tier:user:{user_id}:daily:{YYYY-MM-DD}"

# Cross-account device cap (incremented by every real LLM analysis on the device)
redis-cli KEYS "tier:device:*"
redis-cli GET "tier:device:{device_id}:daily:{YYYY-MM-DD}"

# user_analyzed markers (who already paid for which team)
redis-cli KEYS "user_analyzed:*"

# LLM cache
redis-cli KEYS "llm_cache:*"

# Retry grace tokens
redis-cli KEYS "retry_grace:*"
```

**Expected key states after common flows:**

| Flow | Key | Expected Value |
|------|-----|---------------|
| Anonymous analyzes once | `tier:anon:device:{id}:daily:{date}` | 1 |
| Anonymous analyzes once | `tier:device:{id}:daily:{date}` | 1 |
| Guest analyzes once | `tier:user:{id}:daily:{date}` | 1 |
| Guest analyzes once | `tier:device:{id}:daily:{date}` | 1 (cumulative) |
| Cached hit by new user | `user_analyzed:device:{id}:...` or `user_analyzed:user:{id}:...` | 1 (set) |
| Same user re-analyzes cached | Same `user_analyzed:...` key | 1 (unchanged, TTL reset) |
| New guest created after 1 anonymous analysis | `tier:user:{guest_id}:daily:{date}` | 1 (seeded) |
