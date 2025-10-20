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


def get_rate_limit_key(request: Request) -> str:
    """
    Get rate limit key from request.
    Can be customized to use API keys, user IDs, etc.
    """
    # For now, use IP address
    return get_remote_address(request)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom handler for rate limit exceeded errors.
    """
    logger.warning(
        f"Rate limit exceeded for {get_remote_address(request)} on {request.url.path}"
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": exc.detail,
        },
    )


# Predefined rate limit decorators for common use cases
def analysis_rate_limit():
    """
    Rate limit for expensive analysis endpoints.

    IMPORTANT: Each team analysis makes 6 LLM calls (one per monster).
    Default 3/minute = 18 LLM calls per minute per user.

    Adjust ANALYSIS_RATE_LIMIT in .env based on your needs:
    - "3/minute" = 18 LLM calls/min (conservative)
    - "5/minute" = 30 LLM calls/min (moderate)
    - "10/minute" = 60 LLM calls/min (generous)
    """
    return limiter.limit(ANALYSIS_RATE_LIMIT)


def standard_rate_limit():
    """Standard rate limit for general endpoints."""
    return limiter.limit("100/minute")


def strict_rate_limit():
    """Strict rate limit for sensitive operations."""
    return limiter.limit("10/minute")
