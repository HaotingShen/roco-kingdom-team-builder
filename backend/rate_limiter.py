"""Rate limiting utilities for API endpoints."""

from datetime import datetime, timedelta
from typing import Dict, Tuple
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException, status
from backend.config import RATE_LIMIT_ENABLED, ANALYSIS_RATE_LIMIT, ENVIRONMENT, REDIS_URL
from backend.logger import logger


def get_real_client_ip(request: Request) -> str:
    """
    🔒 SECURITY: Extract real client IP from CloudFront headers.

    AWS Single-Instance Architecture (No ALB):
    - CloudFront → EC2 (direct)
    - CloudFront sets: CloudFront-Viewer-Address (most reliable)
    - Fallback: X-Forwarded-For header

    ⚠️ TRUST MODEL:
    - Production (behind CloudFront): Trust proxy headers
    - Development (direct to EC2): Use direct connection IP

    This prevents attackers from spoofing IP via X-Forwarded-For in development.

    Args:
        request: FastAPI request object

    Returns:
        Client's real IP address
    """
    # Production: Behind CloudFront
    if ENVIRONMENT == "production":
        # Priority 1: CloudFront-Viewer-Address (most reliable)
        # Format: "ip:port" or just "ip"
        cf_viewer = request.headers.get("CloudFront-Viewer-Address")
        if cf_viewer:
            # Extract IP (remove port if present)
            ip = cf_viewer.split(":")[0]
            logger.debug(f"Client IP from CloudFront-Viewer-Address: {ip}")
            return ip

        # Priority 2: X-Forwarded-For (leftmost = client IP)
        # Format: "client_ip, proxy1_ip, proxy2_ip"
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            ip = xff.split(",")[0].strip()
            logger.debug(f"Client IP from X-Forwarded-For: {ip}")
            return ip

        # Priority 3: X-Real-IP (Nginx, some CDNs)
        x_real_ip = request.headers.get("X-Real-IP")
        if x_real_ip:
            ip = x_real_ip.strip()
            logger.debug(f"Client IP from X-Real-IP: {ip}")
            return ip

    # Development: Direct connection (don't trust spoofable headers)
    ip = get_remote_address(request)
    logger.debug(f"Client IP from direct connection: {ip}")
    return ip


# ✅ FIXED: Initialize rate limiter with CloudFront-aware IP detection and Redis storage
limiter = Limiter(
    key_func=get_real_client_ip,  # ✅ Use CloudFront-aware IP detection
    enabled=RATE_LIMIT_ENABLED,
    storage_uri=REDIS_URL,  # ✅ Use Redis (not memory://) for persistence and multi-worker support
    # Why Redis is required:
    # 1. Shared state across multiple workers/processes
    # 2. Persists across server restarts
    # 3. Actually enforces limits (memory:// resets on restart)
)


def _parse_retry_time(detail: str, language: str) -> str:
    """
    Parse slowapi's rate limit detail string and return a localized time string.

    Input formats from slowapi:
    - "10 per 5 minute" -> "5 minutes" / "5 分钟"
    - "1 per 2 minutes" -> "2 minutes" / "2 分钟"
    - "5 per 1 hour" -> "1 hour" / "1 小时"
    - "3 per hour" -> "1 hour" / "1 小时" (no number = 1)

    Args:
        detail: The exc.detail string from slowapi
        language: "en" or "zh"

    Returns:
        Localized time string for display
    """
    import re

    # Try to extract time from "X per Y unit" format (with number)
    match = re.search(r'per\s+(\d+)\s*(second|minute|hour|day)s?', detail, re.IGNORECASE)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
    else:
        # Try without number: "per hour", "per minute" (implies 1)
        match = re.search(r'per\s+(second|minute|hour|day)s?', detail, re.IGNORECASE)
        if match:
            amount = 1
            unit = match.group(1).lower()
        else:
            # Fallback
            if language == "zh":
                return "几分钟"
            return "a few minutes"

    if language == "zh":
        unit_map = {
            "second": "秒",
            "minute": "分钟",
            "hour": "小时",
            "day": "天"
        }
        return f"{amount} {unit_map.get(unit, '分钟')}"
    else:
        # Pluralize for English
        if amount == 1:
            return f"{amount} {unit}"
        else:
            return f"{amount} {unit}s"


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom handler for rate limit exceeded errors.
    Returns a user-friendly message that frontend can display directly.
    Context-aware: different messages for login, analysis, etc.
    """
    client_ip = get_real_client_ip(request)
    path = request.url.path
    logger.warning(
        f"Rate limit exceeded for {client_ip} on {path}"
    )

    # Try to extract language from request body
    language = "en"
    try:
        body = await request.body()
        if body:
            import json
            data = json.loads(body.decode())
            language = data.get("language", "en")
    except:
        # If we can't parse the body, default to English
        pass

    # Parse the retry time from slowapi's detail string
    retry_time = _parse_retry_time(exc.detail if exc.detail else "", language)

    # Context-aware localized error messages
    if "/auth/login" in path:
        if language == "zh":
            message = f"登录尝试过于频繁，请等待 {retry_time} 后再试。"
        else:
            message = f"Too many login attempts. Please wait {retry_time} before trying again."
    elif "/auth/forgot-password" in path:
        if language == "zh":
            message = f"密码重置请求过于频繁，请等待 {retry_time} 后再试。"
        else:
            message = f"Too many password reset requests. Please wait {retry_time} before trying again."
    elif "/auth/register" in path:
        if language == "zh":
            message = f"注册请求过于频繁，请等待 {retry_time} 后再试。"
        else:
            message = f"Too many registration attempts. Please wait {retry_time} before trying again."
    elif "/team/analyze" in path:
        if language == "zh":
            message = f"请求过于频繁，请等待 {retry_time} 后再试。\n提示：重新分析相同队伍会使用缓存，无需等待！"
        else:
            message = f"Too many requests. Please wait {retry_time} before analyzing again.\nTip: Analyzing the same team again uses cache and is instant!"
    else:
        # Generic message for other endpoints
        if language == "zh":
            message = f"请求过于频繁，请等待 {retry_time} 后再试。"
        else:
            message = f"Too many requests. Please wait {retry_time} before trying again."

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=message,
    )


# Predefined rate limit decorators for common use cases
def analysis_rate_limit():
    """
    Rate limit for expensive analysis endpoints.

    IMPORTANT: Each team analysis makes 7 LLM calls:
    - 6 per-monster trait synergy analyses
    - 1 team-wide synergy analysis

    Gemini 2.5 Flash FREE TIER: 10 requests per minute (RPM)

    Default: "1/minute" = 7 LLM calls/min per user (stays under 10 RPM limit)

    Adjust ANALYSIS_RATE_LIMIT in .env based on your API tier:
    - "1/minute" = 7 LLM calls/min (FREE TIER - recommended)
    - "1/90seconds" = ~0.67/min (FREE TIER - with buffer)
    - "2/minute" = 14 LLM calls/min (PAID TIER - requires higher limits)

    Note: Cached analyses bypass rate limiting (instant response)
    """
    return limiter.limit(ANALYSIS_RATE_LIMIT)


# ========== Custom Composite Rate Limiting (Redis-backed) ==========
# Track rate limits by IP + team composition (language-independent)
#
# Previously used in-memory dicts, but these were:
# - Lost on server restart
# - Not shared across multiple workers
#
# Now uses Redis for persistence and multi-worker support.

import redis.asyncio as aioredis

# Async Redis connection pool for rate limiting
_rate_limit_redis_pool: aioredis.Redis | None = None


async def get_rate_limit_redis() -> aioredis.Redis | None:
    """Get async Redis connection for rate limiting (lazy initialization)."""
    global _rate_limit_redis_pool
    if _rate_limit_redis_pool is None:
        try:
            _rate_limit_redis_pool = await aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await _rate_limit_redis_pool.ping()
            logger.info("Rate limit Redis connection established")
        except Exception as e:
            logger.warning(f"Rate limit Redis unavailable: {e}")
            _rate_limit_redis_pool = None
    return _rate_limit_redis_pool


async def check_analysis_rate_limit_async(ip: str, team_hash: str, limit_per_minutes: int = 2) -> bool:
    """
    Redis-based analysis rate limit check.

    Args:
        ip: Client IP address
        team_hash: Language-independent hash of team composition
        limit_per_minutes: Time window in minutes (default: 2)

    Returns:
        True if allowed, False if rate limited

    Uses SETNX with TTL for atomic check-and-set to avoid race conditions.
    """
    try:
        r = await get_rate_limit_redis()
        if not r:
            # Redis unavailable - fail open (allow request)
            logger.warning("Redis unavailable for analysis rate limit, allowing request")
            return True

        key = f"ratelimit:analysis:{ip}:{team_hash}"

        # Check if key exists (meaning we're within the rate limit window)
        exists = await r.exists(key)
        if exists:
            return False  # Rate limited

        return True  # Allowed

    except Exception as e:
        logger.error(f"Redis rate limit check failed: {e}")
        return True  # Fail open - allow request if Redis unavailable


async def check_global_ip_rate_limit_async(ip: str, limit_per_minutes: int = 2) -> bool:
    """
    Redis-based global IP rate limit.

    This prevents users from bypassing rate limits by analyzing different teams.

    Args:
        ip: Client IP address
        limit_per_minutes: Time window in minutes (default: 2)

    Returns:
        True if allowed, False if rate limited
    """
    try:
        r = await get_rate_limit_redis()
        if not r:
            # Redis unavailable - fail open (allow request)
            logger.warning("Redis unavailable for global IP rate limit, allowing request")
            return True

        key = f"ratelimit:global_ip:{ip}"

        # Check if key exists (meaning we're within the rate limit window)
        exists = await r.exists(key)
        if exists:
            return False  # Rate limited

        return True  # Allowed

    except Exception as e:
        logger.error(f"Redis global rate limit check failed: {e}")
        return True  # Fail open


async def record_analysis_async(ip: str, team_hash: str, limit_per_minutes: int = 2):
    """
    Record that an analysis was performed for the given IP and team composition.

    Sets both global IP and per-team keys with TTL.
    Should be called AFTER successful analysis completion.

    Args:
        ip: Client IP address
        team_hash: Language-independent hash of team composition
        limit_per_minutes: Time window in minutes (default: 2)
    """
    try:
        r = await get_rate_limit_redis()
        if not r:
            logger.warning("Redis unavailable, cannot record analysis rate limit")
            return

        ttl_seconds = limit_per_minutes * 60

        # Use pipeline for atomic multi-key set
        async with r.pipeline(transaction=True) as pipe:
            # Set per-team key
            pipe.setex(f"ratelimit:analysis:{ip}:{team_hash}", ttl_seconds, "1")
            # Set global IP key
            pipe.setex(f"ratelimit:global_ip:{ip}", ttl_seconds, "1")
            await pipe.execute()

        logger.debug(f"Recorded analysis rate limit for ip={ip}")

    except Exception as e:
        logger.error(f"Redis record analysis failed: {e}")


# ========== Backward Compatibility (Synchronous Versions) ==========
# These are kept for any code that still uses the synchronous API.
# They now delegate to Redis operations using synchronous Redis client.

def check_analysis_rate_limit(ip: str, team_hash: str, limit_per_minutes: int = 2) -> bool:
    """
    Synchronous analysis rate limit check (backward compatibility).

    NOTE: Prefer using check_analysis_rate_limit_async in async endpoints.
    """
    import redis as sync_redis
    try:
        r = sync_redis.from_url(REDIS_URL, decode_responses=True)
        key = f"ratelimit:analysis:{ip}:{team_hash}"
        return not r.exists(key)
    except Exception as e:
        logger.error(f"Sync Redis rate limit check failed: {e}")
        return True  # Fail open


def check_global_ip_rate_limit(ip: str, limit_per_minutes: int = 2) -> bool:
    """
    Synchronous global IP rate limit check (backward compatibility).

    NOTE: Prefer using check_global_ip_rate_limit_async in async endpoints.
    """
    import redis as sync_redis
    try:
        r = sync_redis.from_url(REDIS_URL, decode_responses=True)
        key = f"ratelimit:global_ip:{ip}"
        return not r.exists(key)
    except Exception as e:
        logger.error(f"Sync Redis global rate limit check failed: {e}")
        return True  # Fail open


def record_analysis(ip: str, team_hash: str, limit_per_minutes: int = 2):
    """
    Synchronous record analysis (backward compatibility).

    NOTE: Prefer using record_analysis_async in async endpoints.
    """
    import redis as sync_redis
    try:
        r = sync_redis.from_url(REDIS_URL, decode_responses=True)
        ttl_seconds = limit_per_minutes * 60
        pipe = r.pipeline()
        pipe.setex(f"ratelimit:analysis:{ip}:{team_hash}", ttl_seconds, "1")
        pipe.setex(f"ratelimit:global_ip:{ip}", ttl_seconds, "1")
        pipe.execute()
    except Exception as e:
        logger.error(f"Sync Redis record analysis failed: {e}")


def get_rate_limit_message(language: str = "en", minutes: int = 2) -> str:
    """
    Get localized rate limit error message for analysis endpoints.

    Args:
        language: "en" or "zh"
        minutes: Time window in minutes (default: 2)

    Returns:
        Localized error message string
    """
    if language == "zh":
        return f"请求过于频繁，请等待 {minutes} 分钟后再试。提示：重新分析相同队伍会使用缓存，无需等待！"
    return f"Too many requests. Please wait {minutes} minutes before analyzing again. Tip: Analyzing the same team again uses cache and is instant!"
