"""Rate limiting utilities for API endpoints."""

from datetime import datetime, timedelta
from typing import Dict, Tuple
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException, status
from backend.config import RATE_LIMIT_ENABLED, ANALYSIS_RATE_LIMIT
from backend.logger import logger


# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    enabled=RATE_LIMIT_ENABLED,
    storage_uri="memory://",  # Use in-memory storage (for Redis: "redis://localhost:6379")
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom handler for rate limit exceeded errors.
    Returns a user-friendly message that frontend can display directly.
    """
    logger.warning(
        f"Rate limit exceeded for {get_remote_address(request)} on {request.url.path}"
    )

    # Extract retry time from exc.detail (e.g., "60 seconds")
    retry_info = exc.detail if exc.detail else "in a moment"

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

    # Localized error messages
    if language == "zh":
        message = f"请求过于频繁，请等待 {retry_info} 后再试。\n提示：重新分析相同队伍会使用缓存，无需等待！"
    else:
        message = f"Too many requests. Please wait {retry_info} before analyzing again.\nTip: Analyzing the same team again uses cache and is instant!"

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


# ========== Custom Composite Rate Limiting ==========
# Track rate limits by IP + team composition (language-independent)

# In-memory storage: {composite_key: (count, window_start)}
_analysis_rate_limit_storage: Dict[str, Tuple[int, datetime]] = {}

# Global IP-only rate limiting (applies to ALL analyses regardless of team)
_global_ip_rate_limit_storage: Dict[str, Tuple[int, datetime]] = {}


def check_analysis_rate_limit(ip: str, team_hash: str, limit_per_minutes: int = 2) -> bool:
    """
    Check if analysis is allowed based on IP + team composition (language-independent).

    Args:
        ip: Client IP address
        team_hash: Language-independent hash of team composition
        limit_per_minutes: Time window in minutes (default: 2)

    Returns:
        True if analysis is allowed, False if rate limit exceeded

    This prevents bypassing rate limits by switching languages for the same team.
    """
    composite_key = f"{ip}:{team_hash}"
    now = datetime.utcnow()

    if composite_key in _analysis_rate_limit_storage:
        count, window_start = _analysis_rate_limit_storage[composite_key]

        # Check if window expired
        if now - window_start > timedelta(minutes=limit_per_minutes):
            # Reset window
            _analysis_rate_limit_storage[composite_key] = (1, now)
            return True

        # Within window - check if limit exceeded
        if count >= 1:  # 1 analysis per window
            return False

        # Increment counter (should not reach here with limit=1, but kept for flexibility)
        _analysis_rate_limit_storage[composite_key] = (count + 1, window_start)
        return True
    else:
        # First analysis for this IP+team combination
        _analysis_rate_limit_storage[composite_key] = (1, now)
        return True


def check_global_ip_rate_limit(ip: str, limit_per_minutes: int = 2) -> bool:
    """
    Check if analysis is allowed based on IP only (global rate limit).

    This prevents users from bypassing rate limits by analyzing different teams.

    Args:
        ip: Client IP address
        limit_per_minutes: Time window in minutes (default: 2)

    Returns:
        True if analysis is allowed, False if rate limit exceeded
    """
    now = datetime.utcnow()

    if ip in _global_ip_rate_limit_storage:
        count, window_start = _global_ip_rate_limit_storage[ip]

        # Check if window expired
        if now - window_start > timedelta(minutes=limit_per_minutes):
            # Reset window
            _global_ip_rate_limit_storage[ip] = (1, now)
            return True

        # Within window - check if limit exceeded
        if count >= 1:  # 1 analysis per window
            return False

        # Increment counter (should not reach here with limit=1, but kept for flexibility)
        _global_ip_rate_limit_storage[ip] = (count + 1, window_start)
        return True
    else:
        # First analysis for this IP
        _global_ip_rate_limit_storage[ip] = (1, now)
        return True


def record_analysis(ip: str, team_hash: str):
    """
    Record that an analysis was performed for the given IP and team composition.

    This updates the rate limit counter for both global IP and IP+team tracking.
    """
    composite_key = f"{ip}:{team_hash}"
    now = datetime.utcnow()
    _analysis_rate_limit_storage[composite_key] = (1, now)
    _global_ip_rate_limit_storage[ip] = (1, now)


def get_rate_limit_message(language: str = "en") -> str:
    """
    Get localized rate limit error message.

    Args:
        language: "en" or "zh"

    Returns:
        Localized error message string
    """
    if language == "zh":
        return "请求过于频繁，请等待后再试。提示：重新分析相同队伍会使用缓存，无需等待！"
    return "Too many requests. Please wait before analyzing again. Tip: Analyzing the same team again uses cache and is instant!"
