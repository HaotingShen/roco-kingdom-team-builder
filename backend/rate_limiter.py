"""Rate limiting utilities for API endpoints."""

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
