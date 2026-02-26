import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# === LLM Provider Configuration ===

# Provider selection: gemini, deepseek
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

# Gemini Configuration (testing - free tier)
# Current free tier limits (Dec 2025): 10 RPM, 20 RPD
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# Gemini Thinking Mode Configuration
# thinking_budget range: 512-24576 tokens (higher = more reasoning depth)
# Default: 24576 (maximum capacity for best quality analysis)
GEMINI_THINKING_BUDGET = int(os.getenv("GEMINI_THINKING_BUDGET", "24576"))

# DeepSeek Official API Configuration (production - for China access)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
# Models: deepseek-chat (非思考模式), deepseek-reasoner (思考模式)
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")
DEEPSEEK_TIMEOUT = float(os.getenv("DEEPSEEK_TIMEOUT", "200.0"))

# LLM Response Configuration
ANALYSIS_TEMPERATURE = float(os.getenv("ANALYSIS_TEMPERATURE", "0.7"))
ANALYSIS_MAX_TOKENS = int(os.getenv("ANALYSIS_MAX_TOKENS", "32768"))

# Validate API keys based on selected provider
if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY required when LLM_PROVIDER=gemini")
elif LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY required when LLM_PROVIDER=deepseek")

# CORS configuration
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS: List[str] = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",")]

# Application settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Database pool settings
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))

# Rate limiting
# IMPORTANT: Each analysis makes 7 LLM calls (6 per-monster + 1 team-wide)
#
# Gemini 2.5 Flash Lite FREE TIER (Dec 2025): 10 RPM, 20 RPD
# - 10 requests per minute (RPM)
# - 20 requests per day (RPD)
# - Very restrictive! Effectively ~2-3 full team analyses per day max
#
# DeepSeek Official API (production): No hard rate limits (queuing system)
#
# Recommended settings:
# - "1/2minutes" = 3.5 LLM calls/min per user (works with Gemini free tier)
# - "1/minute" = 7 LLM calls/min per user (works with Gemini, stays under 10 RPM)
# - "2/minute" = 14 LLM calls/min per user (requires DeepSeek or paid tier)
#
# With caching enabled, repeated analyses are instant (bypasses rate limit)
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
ANALYSIS_RATE_LIMIT = os.getenv("ANALYSIS_RATE_LIMIT", "1/2minutes")

# Reference Resolution
# When enabled, LLM prompts include only referenced game terms instead of all 50+ terms
# Improves signal-to-noise ratio for better analysis quality
# Default: false (safe rollout - enable after validation)
ENABLE_REFERENCE_RESOLUTION = os.getenv("ENABLE_REFERENCE_RESOLUTION", "true").lower() == "true"

# Redis Cache Configuration
# Redis provides persistent cache across restarts and stampede protection
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", "3600"))  # 1 hour default
REDIS_LOCK_TIMEOUT = int(os.getenv("REDIS_LOCK_TIMEOUT", "210"))  # must exceed max LLM response time
REDIS_LOCK_BLOCKING_TIMEOUT = int(os.getenv("REDIS_LOCK_BLOCKING_TIMEOUT", "210"))  # must exceed max LLM response time


# ========== JWT Configuration ==========

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    # Development fallback - MUST be set in production
    if ENVIRONMENT == "production":
        raise ValueError("SECRET_KEY environment variable is required in production")
    SECRET_KEY = "dev-secret-key-DO-NOT-USE-IN-PRODUCTION-min-32-chars"

if len(SECRET_KEY) < 32:
    raise ValueError("SECRET_KEY must be at least 32 characters long")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


# ========== Cookie Configuration (Deployment Topology) ==========

# 🎯 DECISION REQUIRED: Set based on your deployment topology
#
# OPTION A: Same-Site Deployment (RECOMMENDED)
# Frontend: yourdomain.com, API: api.yourdomain.com
# - COOKIE_DOMAIN=.yourdomain.com
# - COOKIE_SAMESITE=lax
# - COOKIE_SECURE=true (production)
#
# OPTION B: Cross-Site Deployment (requires CSRF tokens)
# Frontend: app.vercel.app, API: api.yourdomain.com
# - COOKIE_DOMAIN=
# - COOKIE_SAMESITE=none
# - COOKIE_SECURE=true (REQUIRED with SameSite=None)

COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None) or None  # Set to ".yourdomain.com" in production
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()  # "lax" for same-site, "none" for cross-site
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"  # True in production

# Frontend URL (for CORS and redirects)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Validate SameSite=None requires Secure
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise ValueError("SameSite=None requires Secure=True (HTTPS only)")


# ========== CAPTCHA Configuration (Phase 7A) ==========
#
# Supports multiple CAPTCHA providers:
# - hcaptcha (RECOMMENDED: privacy-focused, free tier available)
# - recaptcha (Google reCAPTCHA v2/v3)
#
# To enable:
# 1. Set CAPTCHA_ENABLED=true
# 2. Set CAPTCHA_SECRET_KEY from your provider's dashboard
# 3. Frontend must include CAPTCHA widget and send token

CAPTCHA_ENABLED = os.getenv("CAPTCHA_ENABLED", "false").lower() == "true"
CAPTCHA_PROVIDER = os.getenv("CAPTCHA_PROVIDER", "hcaptcha")  # "hcaptcha" or "recaptcha"
CAPTCHA_SECRET_KEY = os.getenv("CAPTCHA_SECRET_KEY", "")
CAPTCHA_SITE_KEY = os.getenv("CAPTCHA_SITE_KEY", "")  # Exposed to frontend

# Validate CAPTCHA config
if CAPTCHA_ENABLED and not CAPTCHA_SECRET_KEY:
    raise ValueError("CAPTCHA_SECRET_KEY required when CAPTCHA_ENABLED=true")


# ========== SMTP Email Configuration ==========
#
# Transactional email for:
# - Email verification
# - Password reset
# - Email change confirmation
#
# Uses aiosmtplib for async SMTP to avoid blocking the event loop.
# Falls back to console logging if SMTP is not configured (development).
#
# Common providers:
# - Gmail: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USE_TLS=true
# - SendGrid: SMTP_HOST=smtp.sendgrid.net, SMTP_PORT=587
# - Mailgun: SMTP_HOST=smtp.mailgun.org, SMTP_PORT=587

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "noreply@example.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "RK Team Builder")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"  # STARTTLS on port 587


# ========== Admin Configuration (Phase B) ==========
#
# Admin users are identified by email address (not database flag).
# This keeps admin privileges environment-controlled and more secure.
#
# Usage: Comma-separated list of admin email addresses
# Example: ADMIN_EMAILS=admin@example.com,owner@example.com

ADMIN_EMAILS_STR = os.getenv("ADMIN_EMAILS", "")
ADMIN_EMAILS: List[str] = [
    email.strip().lower()
    for email in ADMIN_EMAILS_STR.split(",")
    if email.strip()
]


# ========== Subscription Tiers (Phase 7A) ==========
#
# Three-tier system with progressive feature gating:
# - anonymous: No account (tracked by device_id + IP)
# - guest: Click "Continue as Guest" (limited teams)
# - free: Registered account (full free features)
# - premium: Paid tier with more analyses
# - unlimited: No limits (admin/special users)

TIER_LIMITS = {
    "anonymous": {
        "daily_analyses": int(os.getenv("TIER_ANONYMOUS_DAILY_ANALYSES", "1")),
        "monthly_analyses": int(os.getenv("TIER_ANONYMOUS_MONTHLY_ANALYSES", "5")),
        "teams_limit": int(os.getenv("TIER_ANONYMOUS_TEAMS_LIMIT", "0")),
        "priority": 0,
    },
    "guest": {
        "daily_analyses": int(os.getenv("TIER_GUEST_DAILY_ANALYSES", "2")),
        "monthly_analyses": int(os.getenv("TIER_GUEST_MONTHLY_ANALYSES", "30")),
        "teams_limit": int(os.getenv("TIER_GUEST_TEAMS_LIMIT", "3")),
        "priority": 0,
    },
    "free": {
        "daily_analyses": int(os.getenv("TIER_FREE_DAILY_ANALYSES", "5")),
        "monthly_analyses": int(os.getenv("TIER_FREE_MONTHLY_ANALYSES", "100")),
        "teams_limit": int(os.getenv("TIER_FREE_TEAMS_LIMIT", "100")),
        "priority": 0,
    },
    "premium": {
        "daily_analyses": int(os.getenv("TIER_PREMIUM_DAILY_ANALYSES", "20")),
        "monthly_analyses": int(os.getenv("TIER_PREMIUM_MONTHLY_ANALYSES", "500")),
        "teams_limit": int(os.getenv("TIER_PREMIUM_TEAMS_LIMIT", "500")),
        "priority": 1,
    },
    "unlimited": {
        "daily_analyses": -1,        # -1 = unlimited (not configurable)
        "monthly_analyses": -1,
        "teams_limit": -1,
        "priority": 2,
    }
}

# Default tier for new users
DEFAULT_TIER = os.getenv("DEFAULT_TIER", "free")

# ========== Cross-Account Daily Caps ==========
#
# Prevents multi-account abuse on the same device/IP.
# Even if a user creates multiple accounts, they share a combined daily budget.
#
# Device cap: Primary tracking via httpOnly cookie (hard to tamper)
# IP cap: Fallback when device_id cookie is missing, also catches VPN abuse
#
# Premium/unlimited users are EXEMPT from these caps.

DEVICE_DAILY_ANALYSIS_CAP = int(os.getenv("DEVICE_DAILY_ANALYSIS_CAP", "5"))
IP_DAILY_ANALYSIS_CAP = int(os.getenv("IP_DAILY_ANALYSIS_CAP", "15"))

# Guest creation rate limit (per IP per day)
GUEST_CREATION_LIMIT_PER_DAY = int(os.getenv("GUEST_CREATION_LIMIT_PER_DAY", "2"))

# Device ID cookie settings
DEVICE_ID_COOKIE_MAX_AGE = int(os.getenv("DEVICE_ID_COOKIE_MAX_AGE", str(365 * 24 * 60 * 60)))  # 1 year

# Retry Grace Configuration
# When analysis partially fails (e.g., 6/7 LLM calls succeed), quota is charged
# immediately. A grace window allows the user to retry for free.
RETRY_GRACE_TTL = int(os.getenv("RETRY_GRACE_TTL", "900"))  # 15 minutes
RETRY_GRACE_MAX_RETRIES = int(os.getenv("RETRY_GRACE_MAX_RETRIES", "3"))  # max free retries per grace window


# ========== Redis Namespace Strategy ==========
#
# All Redis keys use prefixes to prevent collisions:
#
# 1. LLM Cache (cache.py):
#    - Prefix: "llm_cache:"
#    - Format: "llm_cache:{md5_hash}"
#    - TTL: 3600 seconds (1 hour)
#    - Purpose: Cache expensive LLM API responses
#
# 2. Token Revocation (token_revocation.py):
#    - Prefix: "revoked_token:"
#    - Format: "revoked_token:{jti}"
#    - TTL: 604800 seconds (7 days, matches refresh token expiry)
#    - Purpose: Blacklist revoked JWT tokens on logout
#
# 3. Rate Limiting (rate_limiter.py):
#    - Prefix: "rate_limit:" (managed by slowapi)
#    - Format: "rate_limit:{ip}:{endpoint}"
#    - TTL: Varies by limit window (e.g., 120 seconds for 1/2min)
#    - Purpose: Track request counts for rate limiting
#
# 4. Device Daily Cap (tier_limits.py):
#    - Prefix: "tier:device:"
#    - Format: "tier:device:{device_id}:daily:{YYYY-MM-DD}"
#    - TTL: Until midnight UTC
#    - Purpose: Cross-account daily cap per device (prevents multi-account abuse)
#
# 5. IP Daily Cap (tier_limits.py):
#    - Prefix: "tier:ip:"
#    - Format: "tier:ip:{ip}:daily:{YYYY-MM-DD}"
#    - TTL: Until midnight UTC
#    - Purpose: Fallback cap when device_id missing, also abuse signal
#
# 6. Retry Grace (tier_limits.py):
#    - Prefix: "retry_grace:"
#    - Format: "retry_grace:{user|device|ip}:{id}:{team_hash}:{language}"
#    - TTL: RETRY_GRACE_TTL seconds (default 900 = 15 minutes)
#    - Value: Integer counter (starts at RETRY_GRACE_MAX_RETRIES, decremented on each retry)
#    - Purpose: Allow free retry after partial analysis failure (quota already charged)
#
# ⚠️ CRITICAL: All keys MUST have TTL to prevent memory growth!
# Never use SET without SETEX/EXPIRE.