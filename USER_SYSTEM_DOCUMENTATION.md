# User System Documentation

> **Last Updated:** 2026-01-23
> **Status:** Phase 7B Complete (Password Reset)

---

## Table of Contents

1. [Three-Tier System Overview](#three-tier-system-overview)
2. [Tier Limits & Quotas](#tier-limits--quotas)
3. [Authentication Features](#authentication-features)
4. [Backend Endpoints Reference](#backend-endpoints-reference)
5. [Frontend Components](#frontend-components)
6. [Security Features](#security-features)
7. [Known Limitations & Bugs](#known-limitations--bugs)
8. [Missing Frontend UI](#missing-frontend-ui)
9. [Redis Keys Reference](#redis-keys-reference)

---

## Three-Tier System Overview

The system supports three primary user types with different capabilities:

| User Type | Account Status | How to Become | Can Save Teams | Analysis Limit |
|-----------|---------------|---------------|----------------|----------------|
| **Anonymous** | No account | Visit site | No | 1/day |
| **Guest** | Temporary account | Click "Continue as Guest" | Yes (3 max) | 3/day |
| **Registered** | Permanent account | Register with email | Yes (100 max) | 5/day |

### User Journey Flow

```
New Visitor (Anonymous)
    │
    ├─── Click "Log In" ──────────────→ Login Page ───→ Registered User
    │
    ├─── Click "Continue as Guest" ───→ Guest Account Created
    │                                        │
    │                                        └─── Click "Create Account" ──→ Registered User
    │                                                   (preserves teams)
    │
    └─── Click "Create Account" ──────→ Register Page ──→ Registered User
```

---

## Tier Limits & Quotas

### Defined Tiers

| Tier | Daily Analyses | Monthly Analyses | Max Teams | Priority |
|------|---------------|------------------|-----------|----------|
| `anonymous` | 1 | 5 | 0 | 0 |
| `guest` | 3 | 30 | 3 | 0 |
| `free` | 5 | 100 | 100 | 0 |
| `premium` | 20 | 500 | 500 | 1 |
| `unlimited` | ∞ | ∞ | ∞ | 2 |

**Notes:**
- Admin users automatically get `unlimited` tier regardless of `subscription_tier` field
- `-1` values in config mean unlimited
- Priority affects queue order (future feature)

### Anonymous Tracking

Anonymous users are tracked using **dual-key** tracking to prevent bypass:

1. **Device ID** - UUID stored in localStorage (`rktb-device-id`)
2. **IP Address** - Client IP from request headers

The system uses **MAX of both counters** to determine usage, preventing:
- Clearing localStorage to reset device_id
- Using VPN to change IP
- Both simultaneously

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
| Logout All Devices | ✅ | ❌ | Backend only |
| Email Verification | ✅ | ✅ | Working |
| Resend Verification | ✅ | ✅ | Working |
| Password Reset (forgot) | ✅ | ✅ | Working |
| Change Password | ✅ | ❌ | Backend only |
| Change Email | ✅ | ❌ | Backend only |
| Confirm Email Change | ✅ | ❌ | Backend only |
| Delete Account | ✅ | ✅ | Working |
| Guest → Registered Conversion | ✅ | ✅ | Working |
| Admin User Management | ✅ | ✅ | Working |
| Usage/Quota Tracking | ✅ | ❌ | Backend only |

### Guest Account Behavior

- **Creation**: Linked to `device_id` from localStorage
- **Deduplication**: Same device_id returns same guest account
- **Rate Limit**: 2 new guest creations per IP per day
- **Expiry**: Guest accounts expire after 90 days of inactivity (via `last_active_at`)
- **Clear Guest Data**: Generates new device_id, making old guest inaccessible (but still in DB)

### Registered Account Behavior

- **Email Verification**: Required after registration (Phase 7A)
- **Guest Promotion**: When guest registers, teams/data preserved
- **Password Requirements**: 8+ chars, uppercase, lowercase, number
- **Username Requirements**: 3-32 chars, alphanumeric + underscores only

---

## Backend Endpoints Reference

### Core Authentication

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| POST | `/auth/guest` | Create/retrieve guest account | 2/day per IP (new only) |
| POST | `/auth/register` | Register or convert guest | 3/hour |
| POST | `/auth/login` | Login with email/password | 5/15min |
| POST | `/auth/refresh` | Refresh access token | None |
| GET | `/auth/me` | Get current user profile | None |
| POST | `/auth/logout` | Logout (single device) | None |
| POST | `/auth/logout-all` | Logout all devices | None |

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
| `LoginPage.tsx` | `/auth/login` | Login form + "Continue as Guest" |
| `RegisterPage.tsx` | `/auth/register` | Registration form |
| `ForgotPasswordPage.tsx` | `/auth/forgot-password` | Request password reset email |
| `ResetPasswordPage.tsx` | `/auth/reset-password` | Enter token + new password |
| `EmailVerificationModal.tsx` | Modal | Token entry + resend |
| `DeleteAccountModal.tsx` | Modal | Account deletion confirmation |
| `AuthProvider.tsx` | Wrapper | Token refresh, device_id init |
| `authStore.ts` | Store | Zustand state management |

### User Menu (`/frontend/src/components/UserMenu.tsx`)

Shows different UI based on user state:

**Anonymous (user = null):**
- "Log In" button only

**Guest (is_guest = true):**
- Avatar + "Guest" badge
- Create Account
- Log In
- Log Out
- Clear Guest Data

**Registered (is_guest = false):**
- Avatar + username
- Email verification warning (if unverified)
- Profile (TODO)
- Settings (TODO)
- Log Out
- Delete Account

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
| Login attempts | 5 | 15 minutes |
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

1. **Email Service Not Configured**
   - AWS SES credentials not set up
   - Email verification/password reset emails fail silently
   - Workaround: Backend returns `debug_token` in development mode

2. **Analysis Results Not Persisted on Auth Change**
   - If user clicks "Analyze" then logs in/creates guest, analysis results may be lost
   - Analysis is stored in Zustand (persisted to localStorage), but page state may reset

### Functional Limitations

3. **No Change Password UI**
   - Backend endpoint exists (`/auth/change-password`)
   - No settings page to access it

4. **No Change Email UI**
   - Backend endpoints exist (`/auth/change-email`, `/auth/confirm-email-change`)
   - No settings page to access them

5. **No Logout All Devices UI**
   - Backend endpoint exists (`/auth/logout-all`)
   - No button in UserMenu to trigger it

6. **No Usage/Quota Display**
   - Backend endpoints exist (`/auth/usage`, `/auth/quota`)
   - No UI showing remaining analysis quota

7. **Profile Page Not Implemented**
   - "Profile" button in UserMenu does nothing (TODO comment)

8. **Settings Page Not Implemented**
   - "Settings" button in UserMenu does nothing (TODO comment)

### UX Issues

9. **Guest Returning Message Incorrect** (FIXED in this session)
    - Previously always showed "Guest account created" even for returning guests
    - Now shows "Welcome back!" for returning guests

10. **401 Error on Save Team** (FIXED in this session)
    - Previously showed raw "Request failed with status code 401"
    - Now shows SaveTeamModal prompting login/guest creation

11. **Logout Didn't Clear Refresh Token** (FIXED in this session)
    - `clearAuth()` was called before logout API
    - Now logout API is called first to properly revoke token

12. **500 Error on Analyze (No Owner)** (FIXED in this session)
    - `TeamOut.owner_id` was required but inline analysis has no owner
    - Now `owner_id` is optional

13. **No Email Verification Reminder** (FIXED in this session)
    - Registered users with unverified email had no indicator
    - Now shows warning badge + banner in UserMenu

### Technical Debt

14. **Guest Cleanup Script Exists But Not Scheduled**
    - `backend/scripts/cleanup_expired_guests.py` exists
    - No cron job or scheduled task configured

15. **In-Memory Rate Limiting**
    - Some rate limiters use SlowAPI with in-memory storage
    - Resets on server restart
    - Should migrate to Redis for persistence

16. **No Team Limit Enforcement UI**
    - Backend enforces team limits per tier
    - Frontend doesn't show remaining slots or prevent saves when at limit

---

## Missing Frontend UI

### High Priority

| Feature | Backend Endpoint | Priority | Effort |
|---------|------------------|----------|--------|
| Usage/Quota Display | `/auth/quota` | High | Low |

### Medium Priority

| Feature | Backend Endpoint | Priority | Effort |
|---------|------------------|----------|--------|
| Change Password | `/auth/change-password` | Medium | Low |
| Change Email | `/auth/change-email`, `/auth/confirm-email-change` | Medium | Medium |
| Logout All Devices | `/auth/logout-all` | Medium | Low |

### Low Priority

| Feature | Backend Endpoint | Priority | Effort |
|---------|------------------|----------|--------|
| Profile Page | `/auth/me` | Low | Medium |
| Settings Page | N/A | Low | Medium |

---

## Redis Keys Reference

### Usage Tracking

```
tier:user:{user_id}:daily:{YYYY-MM-DD}       # User daily analysis count
tier:user:{user_id}:monthly:{YYYY-MM}         # User monthly analysis count
tier:anon:device:{device_id}:daily:{YYYY-MM-DD}  # Anonymous device daily count
tier:anon:ip:{ip}:daily:{YYYY-MM-DD}          # Anonymous IP daily count
tier:guest_create:ip:{ip}:{YYYY-MM-DD}        # Guest creation count per IP
```

### Rate Limiting

```
rate_limit:analysis:{ip}:{team_hash}          # Per-team rate limit
rate_limit:global:{ip}                        # Global IP rate limit
```

### LLM Cache

```
llm_cache:monster_trait:{hash}                # Monster trait analysis cache
llm_cache:team_synergy:{hash}                 # Team synergy analysis cache
```

### Token Revocation

```
token_blacklist:{jti}                         # Revoked token JTIs
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

# Email (AWS SES)
AWS_SES_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
EMAIL_FROM=noreply@yourdomain.com

# CAPTCHA (optional)
CAPTCHA_ENABLED=false
TURNSTILE_SECRET_KEY=your-secret
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
  "teams_limit": 100,
  "is_anonymous": false,
  "is_guest": false,
  "redis_available": true
}
```

---

## Recommended Improvements

### Immediate (Next Sprint)

1. Add quota display component (show remaining analyses)
2. Configure email service (AWS SES or alternative)
3. Add scheduled job for guest cleanup

### Short-Term

4. Add settings page with:
   - Change password
   - Change email
   - Logout all devices
5. Add team limit warning when approaching max

### Long-Term

6. Implement premium tier payment integration
7. Add OAuth providers (Google, Discord)
8. Add 2FA support
9. Usage analytics dashboard
