# User System Documentation

> **Last Updated:** 2026-03-01
> **Status:** Phase 7G Complete (Concurrent Retry Race Fix + Navigate Fix + Clear Guest Data Fix)

---

## Table of Contents

1. [Three-Tier System Overview](#three-tier-system-overview)
2. [Tier Limits & Quotas](#tier-limits--quotas)
3. [Device Tracking & Cross-Account Caps](#device-tracking--cross-account-caps)
4. [Analysis Retry Grace](#analysis-retry-grace)
5. [Authentication Features](#authentication-features)
   - [Username Validation](#username-validation)
6. [Backend Endpoints Reference](#backend-endpoints-reference)
7. [Frontend Components](#frontend-components)
8. [Security Features](#security-features)
9. [Known Limitations & Bugs](#known-limitations--bugs)
10. [Missing Frontend UI](#missing-frontend-ui)
11. [Redis Keys Reference](#redis-keys-reference)

---

## Three-Tier System Overview

The system supports three primary user types with different capabilities:

| User Type | Account Status | How to Become | Can Save Teams | Analysis Limit |
|-----------|---------------|---------------|----------------|----------------|
| **Anonymous** | No account | Visit site | No | 1/day |
| **Guest** | Temporary account | Click "Continue as Guest" | Yes (3 max) | 3/day |
| **Registered** | Permanent account | Register with email | Yes (20 max) | 5/day |

### User Journey Flow

```
New Visitor (Anonymous)
    │
    ├─── Click "Log In" ──────────────→ Login Page ───→ Registered User
    │
    ├─── Click "Continue as Guest" ───→ Guest Account Created
    │         (only shown if device             │
    │          never had registered)            └─── Click "Create Account" ──→ Registered User
    │                                                      (preserves teams)
    │
    └─── Click "Create Account" ──────→ Register Page ──→ Registered User
```

**Note:** Once a device has been used to register or log in, "Continue as Guest" is permanently hidden on that device. This prevents data fragmentation between guest and registered accounts.

---

## Tier Limits & Quotas

### Defined Tiers

| Tier | Daily Analyses | Monthly Analyses | Max Teams | Priority |
|------|---------------|------------------|-----------|----------|
| `anonymous` | 1 | 5 | 0 | 0 |
| `guest` | 3 | 30 | 3 | 0 |
| `free` | 5 | 100 | 20 | 0 |
| `premium` | 10 | 200 | 100 | 1 |
| `unlimited` | ∞ | ∞ | ∞ | 2 |

**Notes:**
- Admin users automatically get `unlimited` tier regardless of `subscription_tier` field
- `-1` values in config mean unlimited
- Priority affects queue order (future feature)

### Anonymous Tracking

Anonymous users are tracked using **dual-key** tracking to prevent bypass:

1. **Device ID** - UUID stored in httpOnly cookie (`device_id`)
2. **IP Address** - Client IP from request headers

The system uses **MAX of both counters** to determine usage, preventing:
- Clearing cookies to reset device_id (httpOnly = can't be accessed by JS)
- Using VPN to change IP
- Both simultaneously

---

## Device Tracking & Cross-Account Caps

### httpOnly Cookie for Device ID (Phase 7E)

**Previous approach (deprecated):**
- Device ID stored in localStorage (`rktb-device-id`)
- Sent via `X-Device-ID` header
- Problems: XSS could read/modify it, users could easily clear it

**New approach:**
- Device ID stored in httpOnly cookie (`device_id`)
- Set automatically by backend middleware (`DeviceIDMiddleware`)
- Cannot be accessed or modified by JavaScript
- Automatically sent with every request

### Cross-Account Daily Caps

Prevents multi-account abuse on the same device/IP. Even if a user creates multiple accounts, they share a combined daily analysis budget.

| Cap Type | Default | Purpose |
|----------|---------|---------|
| **Device Cap** | 5/day | Primary tracking - all accounts on same device share this limit |
| **IP Cap** | 15/day | Fallback when device_id missing, also catches VPN abuse |

**Exemptions:**
- Premium tier users are exempt from device/IP caps
- Unlimited tier users are exempt from all caps

**Flow:**
```
Analysis Request
      │
      ▼
┌─────────────────────┐
│ 1. Per-User Quota   │  tier:user:{id}:daily
└─────────────────────┘
      │ pass
      ▼
┌─────────────────────┐
│ 2. Device Daily Cap │  tier:device:{device_id}:daily
└─────────────────────┘
      │ pass
      ▼
┌─────────────────────┐
│ 3. IP Daily Cap     │  tier:ip:{ip}:daily
│    (if no device)   │  (fallback only)
└─────────────────────┘
      │ pass
      ▼
    ✅ Allow
```

### Configuration

```bash
# Device/IP caps (in .env)
DEVICE_DAILY_ANALYSIS_CAP=5      # 5 analyses/day per device
IP_DAILY_ANALYSIS_CAP=15         # 15 analyses/day per IP (fallback)
DEVICE_ID_COOKIE_MAX_AGE=31536000  # 1 year
```

### Backend Implementation

| File | Purpose |
|------|---------|
| `main.py` | `DeviceIDMiddleware` - sets httpOnly cookie |
| `tier_limits.py` | `check_device_daily_cap()`, `check_ip_daily_cap()` |
| `config.py` | `DEVICE_DAILY_ANALYSIS_CAP`, `IP_DAILY_ANALYSIS_CAP` |
| `dependencies.py` | `get_device_id()` - reads from cookie |

### Frontend Changes

| Change | Details |
|--------|---------|
| Removed `X-Device-ID` header | Cookie is sent automatically |
| Removed `rktb-device-id` localStorage | No longer needed |
| Updated `authEndpoints.createGuest()` | No longer passes device_id |
| Added `authEndpoints.resetDeviceId()` | For "Clear Guest Data" |

---

## Analysis Retry Grace

### Problem (Phase 7F)

When a team analysis partially fails (e.g., 6/7 LLM calls succeed, 1 gets Gemini 503):

| Behavior | Before 7F | After 7F |
|----------|-----------|----------|
| Quota charged on partial success | No | **Yes** |
| Retry cost | Charged (misleading) | **Free** (via grace window) |
| "Retry (Free)" button label | Inaccurate | **Accurate** |
| Total failure (0/7 succeed) | No charge | No charge (unchanged) |

### How It Works

When an analysis has at least one successful LLM call but not all succeed:

1. **Quota is charged immediately** (the work was done)
2. **A grace marker is set in Redis** with a retry counter (default: 3 retries)
3. On retry, the grace marker is **checked** → **quota checks are bypassed**
4. Rate limits are checked (may reject with 429 — grace counter is **not** consumed)
5. After all pre-flight checks pass, grace counter is **consumed** (decremented) right before analysis starts
6. On successful retry → grace marker is **cleared**
7. If all retries exhausted → grace marker deleted → next attempt treated as fresh (quota checked)

```
Partial Failure (e.g., 6/7 succeed)
      │
      ▼
┌─────────────────────────────┐
│ Charge quota immediately    │
│ Set retry_grace counter = 3 │
└─────────────────────────────┘
      │
      ▼
  User clicks "Retry (Free)"
      │
      ▼
┌─────────────────────────────┐
│ Grace found (check only)    │
│ Skip quota checks           │
└─────────────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ Rate limits checked         │──── 429? Grace NOT consumed.
└─────────────────────────────┘     User can retry later.
      │ pass
      ▼
┌─────────────────────────────┐
│ Consume grace (counter -= 1)│  ← "point of no return"
│ Run analysis                │
└─────────────────────────────┘
      │
      ├── All 7 succeed → Clear grace ✅
      │
      └── Still partial → Counter already decremented
            │                (can retry again)
            └── Counter = 0 → Grace exhausted
                              Next attempt = fresh
```

### Identity Resolution

Grace markers use the **most-specific identity only** to prevent shared-IP (NAT/cafe) exploits:

| Priority | Identity Type | When Used | Redis Key Example |
|----------|--------------|-----------|-------------------|
| 1 (highest) | `user:{id}` | Authenticated user | `retry_grace:user:42:teamhash:zh` |
| 2 | `device:{id}` | Anonymous with known device | `retry_grace:device:dev-001:teamhash:en` |
| 3 (lowest) | `ip:{ip}` | Anonymous, unknown device | `retry_grace:ip:1.2.3.4:teamhash:zh` |

Only **one key** is set per grace event. An authenticated user's grace key is `user:42`, never `device:` or `ip:`.

### Key Isolation

Grace keys include both `team_hash` and `language`, so:

- **Different team composition** → different key → no grace match → fresh attempt
- **Different language** → different key → no grace match → fresh attempt (correct: all cache misses = effectively a new analysis)

### Rate Limits During Grace

Rate limits are **always enforced**, even during grace retries. This protects the Gemini API from abuse. Users may need to wait for the 2-minute rate limit window before retrying. A rate-limited 429 does **not** consume a grace retry — the counter is only decremented after all pre-flight checks pass and the analysis is about to start.

### Fully-Cached Path

When all 7 LLM responses are cached (`is_fully_cached=True`):
- Analysis is instant and free (no quota charge)
- Any lingering grace markers are proactively cleaned up to prevent exploitation if cache entries later expire

### Concurrent Retry Race Fix (Phase 7G)

**Problem:** CloudFront's 120s origin timeout causes the frontend to silently retry a long-running analysis while the first request is still executing. Both concurrent requests could pass `check_analysis_limit` before either one recorded usage, resulting in quota being charged twice (e.g., 0/1 → 2/1).

**Fix:** An `actual_llm_calls` counter is tracked via an `on_compute` callback passed through the cache layer. `on_compute` fires **only when the compute function is actually invoked** (i.e., a true cache miss that triggers real LLM API calls), not on cache hits or lock-wait hits. The second concurrent request waits on the Redis lock, then gets results from cache — its `actual_llm_calls` stays 0, so quota is not charged. Quota is only charged when `actual_llm_calls > 0 and successful_calls > 0`.

| Path | `actual_llm_calls` | Quota charged? |
|------|--------------------|----------------|
| Cache HIT (fast path, no lock) | 0 | No |
| Cache HIT (after waiting for lock) | 0 | No |
| Cache MISS (lock acquired, LLM called) | > 0 | Yes (if any succeed) |

### Configuration

```bash
# Retry grace settings (in .env)
RETRY_GRACE_TTL=900              # Grace window duration (seconds, default: 15 minutes)
RETRY_GRACE_MAX_RETRIES=3        # Max free retries per grace window
```

### Backend Implementation

| File | Purpose |
|------|---------|
| `tier_limits.py` | `set_retry_grace()`, `check_retry_grace()`, `consume_retry_grace()`, `clear_retry_grace()` |
| `tier_limits.py` | `_get_retry_grace_key()`, `_resolve_grace_identity()` (internal helpers) |
| `main.py` | Grace-aware logic in `/team/analyze` and `/team/analyze_by_id` endpoints |
| `config.py` | `RETRY_GRACE_TTL`, `RETRY_GRACE_MAX_RETRIES` |

### Frontend Impact

**No frontend changes required.** The grace mechanism is fully transparent to the frontend:
- The analyze button's `disabled` attribute does not check quota
- The backend returns success/error responses as before
- The "Retry (Free)" button label and messaging are now truthful

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| Daily limit = 1, partial failure | Quota goes to 1/1. Grace allows retry without being blocked by limit check. |
| Grace expires before retry (>15 min) | Treated as fresh attempt, charged normally |
| User at max retries, still failing | Grace exhausted → next attempt is fresh (quota checked) |
| Redis unavailable | `check_retry_grace()` returns `False` (fail closed) — treated as fresh attempt |
| Shared NAT/IP, different users | Only most-specific identity gets grace. User A's grace does not help User B. |

---

## Authentication Features

### Implemented Features

| Feature | Backend | Frontend UI | Status |
|---------|---------|-------------|--------|
| Guest Creation | ✅ | ✅ | Working |
| User Registration | ✅ | ✅ | Working |
| Email/Password Login | ✅ | ✅ | Working |
| Token Refresh | ✅ | ✅ (automatic) | Working |
| Logout (single device) | ✅ | ✅ | Working |
| Logout All Devices | ✅ | ✅ | Merged into registered user "Log Out" |
| Email Verification | ✅ | ✅ | Working |
| Resend Verification | ✅ | ✅ | Working |
| Password Reset (forgot) | ✅ | ✅ | Working |
| Change Password | ✅ | ✅ | Working (Settings page) |
| Change Email | ✅ | ✅ | Working (Settings page) |
| Confirm Email Change | ✅ | ✅ | Working (email link → `/auth/confirm-email-change`) |
| Delete Account | ✅ | ✅ | Working |
| Guest → Registered Conversion | ✅ | ✅ | Working |
| Admin User Management | ✅ | ✅ | Working |
| Usage/Quota Tracking | ✅ | ✅ | Working |

### Guest Account Behavior

- **Creation**: Linked to `device_id` from httpOnly cookie (set by `DeviceIDMiddleware`)
- **Deduplication**: Same device_id returns same guest account
- **Rate Limit**: 2 new guest creations per IP per day
- **Expiry**: Guest accounts expire after 30 days of inactivity (via `last_active_at`; also cleaned up immediately if explicitly orphaned)
- **Clear Guest Data**: Calls `/auth/reset-device-id` to orphan the current guest account (`is_active=False`, `device_id=None`). The device_id cookie is **preserved** so cross-account quota history carries over to any new guest. Requires confirmation before proceeding.
- **Display Name**: Shows as "Guest#XXXX" where XXXX is a unique 4-character alphanumeric ID (e.g., "A2B3")
- **Display ID Generation**: Uses characters `23456789ABCDEFGHJKMNPQRSTUVWXYZ` (excludes confusables: 0/O, 1/I/L)
- **Display ID Uniqueness**: Stored in `guest_display_id` column with unique constraint, guaranteed globally unique
- **Device Restriction**: "Continue as Guest" hidden if device has ever had a registered account (tracked via `rktb-has-registered` in localStorage)
- **Account Deletion Re-enables Guest**: When a registered user deletes their account, `rktb-has-registered` is cleared, allowing them to create a new guest account

### Registered Account Behavior

- **Email Verification**: Required after registration (Phase 7A)
- **Guest Promotion**: When guest registers, teams/data preserved
- **Password Requirements**: 8+ chars, uppercase, lowercase, number
- **Username Requirements**: See [Username Validation](#username-validation) section below

### Username Validation

Usernames support Chinese characters and have comprehensive validation rules.

#### Allowed Characters

| Character Type | Examples | Allowed |
|----------------|----------|---------|
| Latin letters | `A-Z`, `a-z` | ✅ |
| Digits | `0-9` | ✅ |
| Chinese (CJK Unified) | `你好`, `洛克` | ✅ |
| Chinese (CJK Extension A) | Rare characters | ✅ |
| Underscore | `_` | ✅ |
| Hyphen | `-` | ✅ |
| Spaces | ` `, `　` (full-width) | ❌ |
| Emoji | `😀`, `👍` | ❌ |
| Cyrillic | `а`, `о`, `е` | ❌ |
| Greek | `α`, `ο`, `ρ` | ❌ |
| Full-width Latin | `Ａ`, `ｂ` | ❌ |
| Other symbols | `@`, `.`, `#`, `!` | ❌ |

#### Length Requirements

- **Minimum**: 2 graphemes (user-perceived characters)
- **Maximum**: 16 graphemes
- **Counting method**: Grapheme clusters (not bytes), so `你好` = 2 characters

#### Clean Name Rules

| Rule | Valid Examples | Invalid Examples |
|------|----------------|------------------|
| No leading separator | `alan_shen`, `玩家1` | `_alan`, `-player` |
| No trailing separator | `test_user`, `洛克王国` | `alan_`, `player-` |
| No consecutive separators | `alan_shen`, `test-user` | `alan__shen`, `test--user`, `alan_-test` |
| Must contain a letter | `player1`, `玩家1`, `test_123` | `12345`, `123_456` |

#### Pre-processing

- **Whitespace trimming**: Leading/trailing spaces (including full-width `　`) are automatically removed before validation
- **Unicode normalization**: NFC normalization applied for consistent comparison

#### Security: Confusable Character Prevention

The system prevents impersonation attacks using look-alike characters:

| Attack Type | Example | Result |
|-------------|---------|--------|
| Cyrillic substitution | `аdmin` (Cyrillic `а`) | ❌ Blocked (not in allowed chars) |
| Greek substitution | `αdmin` (Greek `α`) | ❌ Blocked (not in allowed chars) |
| Full-width Latin | `Ａｄｍｉｎ` | ❌ Blocked (not in allowed chars) |
| Case variation | `Admin` vs `admin` | ❌ Blocked (canonical match) |

#### Canonical Username Uniqueness

Each username has a **canonical form** stored in the database for uniqueness checking:

```
Original: "TestUser"  →  Canonical: "testuser"
Original: "玩家Test"  →  Canonical: "玩家test"
```

**How it works:**
1. Username is normalized (NFC)
2. Confusable characters are replaced with ASCII equivalents
3. Result is lowercased
4. Checked against existing `canonical_username` column

**Example scenario:**
- User A registers as `admin` → canonical: `admin`
- User B tries to register as `Admin` → canonical: `admin` → **BLOCKED** ("too similar")
- User B tries to register as `administrator` → canonical: `administrator` → **ALLOWED**

#### Reserved Usernames

The following usernames are blocked (case-insensitive):

```
admin, administrator, root, system, api, www,
null, undefined, guest, anonymous, support, help,
moderator, mod, official, staff, team
```

Additionally, any username starting with `guest_` or `guest-` is blocked.

#### Error Messages

| Error | English | Chinese |
|-------|---------|---------|
| Empty | Username cannot be empty | 用户名不能为空 |
| Too short | Must be at least 2 characters | 至少需要2个字符 |
| Too long | Cannot exceed 16 characters | 不能超过16个字符 |
| Has spaces | Cannot contain spaces | 不能包含空格 |
| Has emoji | Cannot contain emoji | 不能包含表情符号 |
| Invalid chars | Only letters, numbers, Chinese, _ and - | 只能包含字母、数字、中文、下划线和连字符 |
| Leading separator | Cannot start with _ or - | 不能以下划线或连字符开头 |
| Trailing separator | Cannot end with _ or - | 不能以下划线或连字符结尾 |
| Consecutive separators | Cannot contain consecutive _ or - | 不能包含连续的下划线或连字符 |
| Needs letter | Must contain at least one letter | 必须包含至少一个字母或汉字 |
| Too similar | Too similar to existing username | 与已存在的用户名过于相似 |
| Taken | Already taken | 已被使用 |

#### Implementation Files

| File | Purpose |
|------|---------|
| `backend/username_validator.py` | Core validation logic, canonical normalization |
| `backend/schemas.py` | Pydantic validator integration |
| `backend/main.py` | Registration endpoint with canonical check |
| `backend/models.py` | `canonical_username` column definition |
| `frontend/src/lib/usernameValidator.ts` | Client-side validation |
| `frontend/src/i18n.tsx` | Localized error messages |

#### Database Schema

```sql
-- users table
username           VARCHAR(64) NOT NULL UNIQUE,
canonical_username VARCHAR(64) NOT NULL UNIQUE,  -- For uniqueness check
guest_display_id   VARCHAR(8) UNIQUE,             -- Unique 4-char ID for guests (e.g., "A2B3")
```

Migrations:
- `e1f2g3h4i5j6_add_canonical_username_to_users.py`
- `f1g2h3i4j5k6_add_guest_display_id.py`

---

## Backend Endpoints Reference

### Core Authentication

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| POST | `/auth/guest` | Create/retrieve guest account | 2/day per IP (new only) |
| POST | `/auth/register` | Register or convert guest | 3/hour |
| POST | `/auth/login` | Login with email/password | 10/5min |
| POST | `/auth/refresh` | Refresh access token | None |
| GET | `/auth/me` | Get current user profile | None |
| POST | `/auth/logout` | Logout (single device) | None |
| POST | `/auth/logout-all` | Logout all devices | None |
| POST | `/auth/reset-device-id` | Orphan current guest account (preserves device_id cookie) | None |

### Email Verification (Phase 7A)

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| POST | `/auth/verify-email` | Verify with token | 10/hour |
| POST | `/auth/resend-verification` | Resend verification email | 3/hour |

### Password Management

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| POST | `/auth/forgot-password` | Request reset email | 3/hour |
| POST | `/auth/reset-password` | Reset with token | 5/hour |
| POST | `/auth/change-password` | Change while logged in | None |

### Email Change (Phase 6)

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| POST | `/auth/change-email` | Request email change | 3/hour |
| POST | `/auth/confirm-email-change` | Confirm with token | 5/hour |

### Account Management

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| DELETE | `/auth/account` | Delete account permanently | None |
| GET | `/auth/usage` | Get usage statistics | None |
| GET | `/auth/quota` | Get quota info | None |

### Admin Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/admin/users` | List users (paginated) | Admin |
| GET | `/admin/users/{id}` | Get user details | Admin |
| PUT | `/admin/users/{id}/tier` | Change user tier | Admin |
| POST | `/admin/users/{id}/lock` | Lock user account | Admin |
| POST | `/admin/users/{id}/unlock` | Unlock user account | Admin |
| DELETE | `/admin/users/{id}` | Delete user | Admin |
| GET | `/admin/stats` | System statistics | Admin |
| POST | `/admin/database/reset-users` | Reset all users (DEV) | Admin |

---

## Frontend Components

### Auth Pages (`/frontend/src/features/auth/`)

| Component | Route | Purpose |
|-----------|-------|---------|
| `LoginPage.tsx` | `/auth/login` | Login form + "Continue as Guest" (conditional) |
| `RegisterPage.tsx` | `/auth/register` | Registration form |
| `ForgotPasswordPage.tsx` | `/auth/forgot-password` | Request password reset email |
| `ResetPasswordPage.tsx` | `/auth/reset-password` | Enter token + new password |
| `EmailVerificationModal.tsx` | Modal | Token entry + resend |
| `DeleteAccountModal.tsx` | Modal | Account deletion confirmation |
| `ClearGuestDataModal.tsx` | Modal | Guest data clearing confirmation |
| `AuthProvider.tsx` | Wrapper | Token refresh, device_id init |
| `authStore.ts` | Store | Zustand state management, `hasDeviceRegistered()` |

### App Infrastructure (`/frontend/src/components/`)

| Component | Purpose |
|-----------|---------|
| `AppReadyProvider.tsx` | Waits for auth + essential data before hiding loading screen |
| `SaveTeamModal.tsx` | Prompts anonymous users to login/register/guest when saving |

### User Menu (`/frontend/src/components/UserMenu.tsx`)

Shows different UI based on user state:

**Anonymous (user = null):**
- "Log In" button only

**Guest (is_guest = true):**
- Avatar + "Guest#XXXX" display name (4-character alphanumeric ID from `guest_display_id`)
- Create Account
- Log In
- Log Out
- Clear Guest Data (with confirmation modal)

**Registered (is_guest = false):**
- Avatar + username
- Email verification warning (if unverified)
- Profile (TODO — not yet implemented)
- Settings (Change Password, Change Email)
- Log Out
- Delete Account

**Logout Behavior:**
- **Registered users:** Calls `/auth/logout-all` (increments `token_version`, invalidates all sessions on all devices immediately)
- **Guest users:** Calls `/auth/logout` (revokes current refresh token only; guest account persists for reclaim via "Continue as Guest")
- Both: Clears React Query cache to prevent data leakage between users

### Admin Pages (`/frontend/src/features/admin/`)

| Component | Purpose |
|-----------|---------|
| `AdminPage.tsx` | Dashboard with tabs |
| `UserTable.tsx` | User listing with actions |
| `UserModal.tsx` | User details modal |

---

## Security Features

### Token Security

| Token Type | Lifetime | Storage | Security |
|------------|----------|---------|----------|
| Access Token | 15 minutes | Memory only (JS) | Short-lived, not persisted |
| Refresh Token | 7 days | httpOnly cookie | Cannot be accessed by JS |
| CSRF Token | Embedded in access token | N/A | For cross-site deployments |

### Password Security

- **Hashing**: bcrypt with 12 rounds
- **Comparison**: Constant-time (prevents timing attacks)
- **Requirements**: 8+ chars, uppercase, lowercase, number
- **Session Invalidation**: All sessions invalidated on password change

### Account Lockout

- **Threshold**: 10 failed login attempts
- **Duration**: 30 minutes (automatic unlock)
- **Counter Reset**: On successful login
- **Admin Override**: Can unlock manually

### Rate Limiting Summary

| Action | Limit | Window |
|--------|-------|--------|
| Login attempts | 10 | 5 minutes |
| Registration | 3 | 1 hour |
| Guest creation (new) | 2 | 1 day |
| Email verification | 10 | 1 hour |
| Resend verification | 3 | 1 hour |
| Password reset request | 3 | 1 hour |
| Password reset confirm | 5 | 1 hour |
| Email change request | 3 | 1 hour |

### Anti-Abuse Measures

1. **Email Cooldown**: 30-day cooldown on deleted account emails
2. **User Enumeration Prevention**: Uniform error messages, password reset always returns success
3. **CAPTCHA Support**: Integration points exist (not currently enabled)
4. **DNS Email Validation**: Email addresses checked for valid MX records

---

## Known Limitations & Bugs

### Critical Issues

1. ~~**Email Service Not Configured**~~ (FIXED)
   - Production uses Resend via SMTP (`noreply@rkteambuilder.com`)
   - Development still returns `debug_token` when SMTP is not configured

2. **Analysis Results Not Persisted on Auth Change**
   - If user clicks "Analyze" then logs in/creates guest, analysis results may be lost
   - Analysis is stored in Zustand (persisted to localStorage), but page state may reset

### Functional Limitations

3. ~~**No Change Password UI**~~ (FIXED)
   - Settings page (`/settings`) implemented with Change Password form

4. ~~**No Change Email UI**~~ (FIXED)
   - Settings page (`/settings`) implemented with Change Email form

5. ~~**No Logout All Devices UI**~~ (FIXED)
   - Registered user "Log Out" now calls `/auth/logout-all` (invalidates all sessions on all devices)
   - Guest "Log Out" still calls `/auth/logout` (single-device, guest account persists for reclaim)

6. **No Usage/Quota/Limit Display** (FIXED)
   - Quota display added to UserMenu dropdown (tier badge, analysis usage, team count)
   - Inline team count shown on TeamsListPage heading
   - Save button disabled and shows warning when at team limit
   - Analyze button shows remaining daily count (e.g., "2/5")
   - Quota auto-refreshes after save, delete, and analyze actions

7. **Profile Page Not Implemented**
   - "Profile" button in UserMenu does nothing (TODO comment)

8. ~~**Settings Page Not Implemented**~~ (FIXED)
   - Settings page at `/settings` implements Change Password and Change Email

### UX Issues

9. **Guest Returning Message Incorrect** (FIXED)
    - Previously always showed "Guest account created" even for returning guests
    - Now shows "Welcome back!" for returning guests

10. **401 Error on Save Team** (FIXED)
    - Previously showed raw "Request failed with status code 401"
    - Now shows SaveTeamModal prompting login/guest creation

11. **Logout Didn't Clear Refresh Token** (FIXED)
    - `clearAuth()` was called before logout API
    - Now logout API is called first to properly revoke token

12. **500 Error on Analyze (No Owner)** (FIXED in this session)
    - `TeamOut.owner_id` was required but inline analysis has no owner
    - Now `owner_id` is optional

13. **No Email Verification Reminder** (FIXED)
    - Registered users with unverified email had no indicator
    - Now shows warning badge + banner in UserMenu

14. **Blank Screen Flash on Load** (FIXED)
    - Loading screen disappeared before auth was ready
    - Now uses `AppReadyProvider` to wait for auth + essential data

15. **Guest Option Shown After Registration** (FIXED)
    - User could create separate guest account after registering
    - Now "Continue as Guest" hidden if device has registered (`rktb-has-registered`)

16. **Teams Visible After Logout** (FIXED)
    - React Query cache not cleared on logout
    - Now `queryClient.clear()` called in all logout handlers

17. **Clear Guest Data Had No Confirmation** (FIXED)
    - Destructive action had no warning
    - Now shows `ClearGuestDataModal` with warning before clearing

### Technical Debt

18. ~~**Guest Cleanup Script Exists But Not Scheduled**~~ (FIXED)
    - `_periodic_guest_cleanup()` background task runs in-process every 24 hours on startup
    - Deletes explicitly orphaned guests (`is_active=False`) and guests inactive for 30+ days
    - Uses a Redis distributed lock so only one uvicorn worker runs per cycle (production uses `--workers 2`)

---

## Missing Frontend UI

### High Priority

| Feature | Backend Endpoint | Priority | Status |
|---------|------------------|----------|--------|
| ~~Usage/Quota/Limit Display~~ | `/auth/quota` | High | Done |

### Medium Priority

| Feature | Backend Endpoint | Priority | Status |
|---------|------------------|----------|--------|
| ~~Change Password~~ | `/auth/change-password` | Medium | Done (Settings page) |
| ~~Change Email~~ | `/auth/change-email`, `/auth/confirm-email-change` | Medium | Done (Settings page) |
| ~~Logout All Devices~~ | `/auth/logout-all` | Medium | Done (merged into Log Out for registered users) |

### Low Priority

| Feature | Backend Endpoint | Priority | Status |
|---------|------------------|----------|--------|
| Profile Page | `/auth/me` | Low | Pending |
| ~~Settings Page~~ | N/A | Low | Done |

---

## Redis Keys Reference

### Per-User Usage Tracking

```
tier:user:{user_id}:daily:{YYYY-MM-DD}       # User daily analysis count
tier:user:{user_id}:monthly:{YYYY-MM}         # User monthly analysis count
tier:anon:device:{device_id}:daily:{YYYY-MM-DD}  # Anonymous device daily count
tier:anon:ip:{ip}:daily:{YYYY-MM-DD}          # Anonymous IP daily count
tier:guest_create:ip:{ip}:{YYYY-MM-DD}        # Guest creation count per IP
```

### Cross-Account Daily Caps (Phase 7E)

```
tier:device:{device_id}:daily:{YYYY-MM-DD}   # Device daily cap (5/day default)
tier:ip:{ip}:daily:{YYYY-MM-DD}              # IP daily cap (15/day fallback)
```

**Note:** These caps apply ACROSS ALL accounts on the same device/IP, preventing multi-account abuse. Premium/unlimited users are exempt.

### Retry Grace (Phase 7F)

```
retry_grace:user:{user_id}:{team_hash}:{language}      # Authenticated user grace
retry_grace:device:{device_id}:{team_hash}:{language}   # Anonymous device grace
retry_grace:ip:{ip}:{team_hash}:{language}              # Anonymous IP grace (last resort)
```

**Value:** Integer counter (starts at `RETRY_GRACE_MAX_RETRIES`, decremented on each retry)
**TTL:** `RETRY_GRACE_TTL` seconds (default 900 = 15 minutes)

**Note:** Only ONE key is set per grace event using the most-specific identity (user > device > IP).

### Rate Limiting

```
ratelimit:analysis:{ip}:{team_hash}          # Per-team rate limit (1min TTL)
```

### LLM Cache

```
llm_cache:monster_trait:{hash}                # Monster trait analysis cache
llm_cache:team_synergy:{hash}                 # Team synergy analysis cache
```

### Token Revocation

```
revoked_token:{jti}                           # Revoked token JTIs (httpOnly refresh tokens)
```

---

## Environment Variables

### Required

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/roco_kingdom
SECRET_KEY=your-jwt-secret-key
GEMINI_API_KEY=your-gemini-api-key
```

### Optional Auth Config

```bash
# Token lifetimes
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Cookie settings
COOKIE_SAMESITE=lax              # lax, strict, or none
COOKIE_SECURE=true               # Set false for localhost

# Rate limiting
RATE_LIMIT_ENABLED=true
ANALYSIS_RATE_LIMIT=1/2minutes

# Cross-account daily caps (Phase 7E)
DEVICE_DAILY_ANALYSIS_CAP=5      # Max analyses per device per day
IP_DAILY_ANALYSIS_CAP=15         # Max analyses per IP per day (fallback)
DEVICE_ID_COOKIE_MAX_AGE=31536000  # 1 year in seconds

# Retry grace (Phase 7F)
RETRY_GRACE_TTL=900              # Grace window duration in seconds (default: 15 min)
RETRY_GRACE_MAX_RETRIES=3        # Max free retries per grace window

# Email (SMTP — production uses Resend)
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USER=resend
SMTP_PASSWORD=your-resend-api-key
EMAIL_FROM=noreply@rkteambuilder.com

# CAPTCHA (optional)
CAPTCHA_ENABLED=false
CAPTCHA_PROVIDER=hcaptcha          # "hcaptcha" or "recaptcha"
CAPTCHA_SECRET_KEY=your-secret
CAPTCHA_SITE_KEY=your-site-key     # Exposed to frontend
```

---

## API Response Examples

### Guest Creation (New)
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 123,
    "username": "guest_abc123def456",
    "email": null,
    "is_guest": true,
    "guest_display_id": "A2B3",
    "email_verified": false,
    "subscription_tier": "guest",
    "created_at": "2026-01-23T12:00:00Z"
  },
  "is_returning_guest": false
}
```

### Guest Creation (Returning)
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": { ... },
  "is_returning_guest": true
}
```

### Quota Response
```json
{
  "tier": "free",
  "daily_used": 2,
  "daily_limit": 5,
  "monthly_used": 15,
  "monthly_limit": 100,
  "teams_used": 3,
  "teams_limit": 20,
  "is_anonymous": false,
  "is_guest": false,
  "redis_available": true
}
```

---

## Recommended Improvements

### Immediate (Next Sprint)

1. ~~Add quota display component (show remaining analyses)~~ Done
2. ~~Configure email service~~ Done (Resend via SMTP)
3. ~~Add scheduled job for guest cleanup~~ Done (`_periodic_guest_cleanup` runs every 24 hours)

### Short-Term

4. ~~Add settings page with Change Password and Change Email~~ Done
5. ~~Add Logout All Devices to Settings page~~ Done (merged into Log Out)
6. Add team limit warning when approaching max

### Long-Term

6. Implement premium tier payment integration
7. Add OAuth providers (Google, Discord)
8. Add 2FA support
9. Usage analytics dashboard
