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

# LLM Response Configuration
ANALYSIS_TEMPERATURE = float(os.getenv("ANALYSIS_TEMPERATURE", "0.7"))
ANALYSIS_MAX_TOKENS = int(os.getenv("ANALYSIS_MAX_TOKENS", "4096"))

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
ENABLE_REFERENCE_RESOLUTION = os.getenv("ENABLE_REFERENCE_RESOLUTION", "false").lower() == "true"

# Redis Cache Configuration
# Redis provides persistent cache across restarts and stampede protection
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", "3600"))  # 1 hour default
REDIS_LOCK_TIMEOUT = int(os.getenv("REDIS_LOCK_TIMEOUT", "30"))  # 30 seconds for lock timeout
REDIS_LOCK_BLOCKING_TIMEOUT = int(os.getenv("REDIS_LOCK_BLOCKING_TIMEOUT", "60"))  # 60 seconds to wait for lock


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
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Roco Kingdom Team Builder")
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
        "daily_analyses": 1,         # 1 analysis per day
        "monthly_analyses": 5,       # 5 analyses per month
        "teams_limit": 0,            # Cannot save teams (must sign up)
        "priority": 0,
    },
    "guest": {
        "daily_analyses": 3,         # 3 analyses per day
        "monthly_analyses": 30,      # 30 analyses per month
        "teams_limit": 3,            # Max 3 saved teams
        "priority": 0,
    },
    "free": {
        "daily_analyses": 5,         # 5 analyses per day
        "monthly_analyses": 100,     # 100 analyses per month
        "teams_limit": 100,          # Max 100 saved teams
        "priority": 0,
    },
    "premium": {
        "daily_analyses": 20,
        "monthly_analyses": 500,
        "teams_limit": 500,
        "priority": 1,
    },
    "unlimited": {
        "daily_analyses": -1,        # -1 = unlimited
        "monthly_analyses": -1,
        "teams_limit": -1,
        "priority": 2,
    }
}

# Default tier for new users
DEFAULT_TIER = os.getenv("DEFAULT_TIER", "free")


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
# ⚠️ CRITICAL: All keys MUST have TTL to prevent memory growth!
# Never use SET without SETEX/EXPIRE.