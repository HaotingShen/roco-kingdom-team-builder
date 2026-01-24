"""Tier-based analysis limits (Phase 7A).

Tracks and enforces analysis limits based on user subscription tier.

Features:
- Daily and monthly analysis limits per tier
- Team count limits
- Redis-backed usage tracking with automatic TTL
- Graceful degradation (allows on Redis failure)

Usage:
    from backend.tier_limits import check_analysis_limit, record_analysis_usage

    # In analysis endpoint:
    await check_analysis_limit(user, db)  # Raises 429 if limit exceeded
    # ... perform analysis ...
    await record_analysis_usage(user)  # Increment usage counters
"""

import redis
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from backend.config import TIER_LIMITS, REDIS_URL
from backend.logger import logger
from backend import models


# Redis client for usage tracking
_redis: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """Get Redis client for tier limits (lazy initialization)."""
    global _redis
    if _redis is None:
        try:
            _redis = redis.from_url(REDIS_URL, decode_responses=True)
            _redis.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable for tier limits: {e}")
            _redis = None
    return _redis


def _get_user_key(user_id: int, period: str) -> str:
    """Generate Redis key for user's analysis count.

    Args:
        user_id: User ID
        period: "daily" or "monthly"

    Returns:
        Redis key like "tier:user:123:daily:2024-01-15" or "tier:user:123:monthly:2024-01"
    """
    now = datetime.now(timezone.utc)
    if period == "daily":
        date_str = now.strftime("%Y-%m-%d")
    else:  # monthly
        date_str = now.strftime("%Y-%m")
    return f"tier:user:{user_id}:{period}:{date_str}"


def get_tier_limits(tier: str) -> Dict[str, Any]:
    """Get limits for a subscription tier."""
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


def get_effective_tier(user: models.User) -> str:
    """
    Get effective tier for a user, considering admin status.

    Admins automatically get 'unlimited' tier regardless of their
    subscription_tier setting in the database.

    Args:
        user: User model instance

    Returns:
        Effective tier string ('unlimited' for admins, otherwise user's tier)
    """
    from backend.dependencies import is_admin_user

    if is_admin_user(user):
        return "unlimited"
    return user.subscription_tier or "free"


async def get_usage_stats(user: models.User) -> Dict[str, Any]:
    """Get current usage statistics for a user.

    Returns:
        Dictionary with daily_used, monthly_used, and limits
    """
    tier = get_effective_tier(user)
    limits = get_tier_limits(tier)

    redis_client = get_redis()
    if not redis_client:
        # Redis unavailable - return zero usage (fail open)
        return {
            "tier": tier,
            "daily_used": 0,
            "daily_limit": limits["daily_analyses"],
            "monthly_used": 0,
            "monthly_limit": limits["monthly_analyses"],
            "teams_limit": limits["teams_limit"],
            "redis_available": False
        }

    try:
        daily_key = _get_user_key(user.id, "daily")
        monthly_key = _get_user_key(user.id, "monthly")

        daily_used = int(redis_client.get(daily_key) or 0)
        monthly_used = int(redis_client.get(monthly_key) or 0)

        return {
            "tier": tier,
            "daily_used": daily_used,
            "daily_limit": limits["daily_analyses"],
            "monthly_used": monthly_used,
            "monthly_limit": limits["monthly_analyses"],
            "teams_limit": limits["teams_limit"],
            "redis_available": True
        }
    except Exception as e:
        logger.error(f"Failed to get usage stats for user {user.id}: {e}")
        return {
            "tier": tier,
            "daily_used": 0,
            "daily_limit": limits["daily_analyses"],
            "monthly_used": 0,
            "monthly_limit": limits["monthly_analyses"],
            "teams_limit": limits["teams_limit"],
            "redis_available": False
        }


async def check_analysis_limit(user: models.User, db: Session) -> None:
    """Check if user is within their analysis limits.

    Args:
        user: User model instance
        db: Database session

    Raises:
        HTTPException 429: If user has exceeded their tier limits
    """
    tier = get_effective_tier(user)
    limits = get_tier_limits(tier)

    # Unlimited tier bypasses all checks
    if limits["daily_analyses"] == -1:
        return

    redis_client = get_redis()
    if not redis_client:
        # Redis unavailable - fail open (allow the request)
        logger.warning(f"Redis unavailable, allowing analysis for user {user.id}")
        return

    try:
        daily_key = _get_user_key(user.id, "daily")
        monthly_key = _get_user_key(user.id, "monthly")

        daily_used = int(redis_client.get(daily_key) or 0)
        monthly_used = int(redis_client.get(monthly_key) or 0)

        # Check daily limit
        if daily_used >= limits["daily_analyses"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily analysis limit reached ({limits['daily_analyses']} per day for {tier} tier). "
                       f"Upgrade to premium for more analyses.",
                headers={"X-Tier-Limit-Type": "daily"}
            )

        # Check monthly limit
        if limits["monthly_analyses"] != -1 and monthly_used >= limits["monthly_analyses"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Monthly analysis limit reached ({limits['monthly_analyses']} per month for {tier} tier). "
                       f"Upgrade to premium for more analyses.",
                headers={"X-Tier-Limit-Type": "monthly"}
            )

    except HTTPException:
        raise
    except Exception as e:
        # Redis error - fail open
        logger.error(f"Failed to check tier limits for user {user.id}: {e}")


async def record_analysis_usage(user: models.User) -> None:
    """Record an analysis usage for a user.

    Should be called AFTER successful analysis completion.
    Increments both daily and monthly counters.
    """
    redis_client = get_redis()
    if not redis_client:
        logger.warning(f"Redis unavailable, cannot record analysis for user {user.id}")
        return

    try:
        daily_key = _get_user_key(user.id, "daily")
        monthly_key = _get_user_key(user.id, "monthly")

        # Use pipeline for atomic increment
        pipe = redis_client.pipeline()

        # Increment daily counter (expires at midnight UTC)
        pipe.incr(daily_key)
        # Calculate seconds until midnight UTC
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_ttl = int((tomorrow - now).total_seconds())
        pipe.expire(daily_key, daily_ttl)

        # Increment monthly counter (expires at end of month)
        pipe.incr(monthly_key)
        # Calculate seconds until end of month
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        monthly_ttl = int((next_month - now).total_seconds())
        pipe.expire(monthly_key, monthly_ttl)

        pipe.execute()

        logger.debug(f"Recorded analysis for user {user.id} ({user.subscription_tier} tier)")

    except Exception as e:
        logger.error(f"Failed to record analysis usage for user {user.id}: {e}")


async def check_teams_limit(user: models.User, db: Session) -> None:
    """Check if user can create more teams.

    Args:
        user: User model instance
        db: Database session

    Raises:
        HTTPException 403: If user has reached their teams limit
    """
    tier = get_effective_tier(user)
    limits = get_tier_limits(tier)

    # Unlimited tier bypasses checks
    if limits["teams_limit"] == -1:
        return

    # Count user's teams
    team_count = db.query(models.Team).filter(models.Team.owner_id == user.id).count()

    if team_count >= limits["teams_limit"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Team limit reached ({limits['teams_limit']} teams for {tier} tier). "
                   f"Delete some teams or upgrade to premium.",
            headers={"X-Tier-Limit-Type": "teams"}
        )


# ========== Anonymous User Tracking ==========
#
# Tracks anonymous users via dual-key approach:
# - device_id (from localStorage, sent via X-Device-ID header)
# - IP address (for abuse prevention)
#
# Both are tracked INDEPENDENTLY. User must bypass BOTH to circumvent limits.
# This prevents:
# - Clearing localStorage (IP still blocks)
# - VPN hopping (device_id still blocks)


def _get_anonymous_device_key(device_id: str, period: str) -> str:
    """Generate Redis key for anonymous user's analysis count by device_id.

    Args:
        device_id: Device identifier from localStorage
        period: "daily" or "monthly"

    Returns:
        Redis key like "tier:anon:device:{device_id}:daily:2024-01-15"
    """
    now = datetime.now(timezone.utc)
    if period == "daily":
        date_str = now.strftime("%Y-%m-%d")
    else:  # monthly
        date_str = now.strftime("%Y-%m")
    return f"tier:anon:device:{device_id}:{period}:{date_str}"


def _get_anonymous_ip_key(ip: str, period: str) -> str:
    """Generate Redis key for anonymous user's analysis count by IP.

    Args:
        ip: Client IP address
        period: "daily" or "monthly"

    Returns:
        Redis key like "tier:anon:ip:{ip}:daily:2024-01-15"
    """
    now = datetime.now(timezone.utc)
    if period == "daily":
        date_str = now.strftime("%Y-%m-%d")
    else:  # monthly
        date_str = now.strftime("%Y-%m")
    return f"tier:anon:ip:{ip}:{period}:{date_str}"


async def get_anonymous_usage_stats(device_id: str, ip: str) -> Dict[str, Any]:
    """Get current usage statistics for an anonymous user.

    Args:
        device_id: Device identifier from localStorage
        ip: Client IP address

    Returns:
        Dictionary with daily_used, monthly_used, and limits
    """
    limits = get_tier_limits("anonymous")

    redis_client = get_redis()
    if not redis_client:
        # Redis unavailable - return zero usage (fail open)
        return {
            "tier": "anonymous",
            "daily_used": 0,
            "daily_limit": limits["daily_analyses"],
            "monthly_used": 0,
            "monthly_limit": limits["monthly_analyses"],
            "teams_limit": limits["teams_limit"],
            "redis_available": False
        }

    try:
        # Get counts from both device and IP tracking
        device_daily_key = _get_anonymous_device_key(device_id, "daily")
        device_monthly_key = _get_anonymous_device_key(device_id, "monthly")
        ip_daily_key = _get_anonymous_ip_key(ip, "daily")
        ip_monthly_key = _get_anonymous_ip_key(ip, "monthly")

        device_daily = int(redis_client.get(device_daily_key) or 0)
        device_monthly = int(redis_client.get(device_monthly_key) or 0)
        ip_daily = int(redis_client.get(ip_daily_key) or 0)
        ip_monthly = int(redis_client.get(ip_monthly_key) or 0)

        # Return the HIGHER count (more restrictive)
        # This prevents bypass by clearing localStorage (IP count remains)
        # or using VPN (device count remains)
        daily_used = max(device_daily, ip_daily)
        monthly_used = max(device_monthly, ip_monthly)

        return {
            "tier": "anonymous",
            "daily_used": daily_used,
            "daily_limit": limits["daily_analyses"],
            "monthly_used": monthly_used,
            "monthly_limit": limits["monthly_analyses"],
            "teams_limit": limits["teams_limit"],
            "redis_available": True
        }
    except Exception as e:
        logger.error(f"Failed to get anonymous usage stats: {e}")
        return {
            "tier": "anonymous",
            "daily_used": 0,
            "daily_limit": limits["daily_analyses"],
            "monthly_used": 0,
            "monthly_limit": limits["monthly_analyses"],
            "teams_limit": limits["teams_limit"],
            "redis_available": False
        }


async def check_anonymous_analysis_limit(device_id: str, ip: str) -> None:
    """Check if anonymous user is within their analysis limits.

    Uses dual-key tracking (device_id AND IP) to prevent abuse.
    User is blocked if EITHER device_id OR IP has hit the limit.

    Args:
        device_id: Device identifier from localStorage
        ip: Client IP address

    Raises:
        HTTPException 429: If user has exceeded anonymous tier limits
    """
    limits = get_tier_limits("anonymous")

    redis_client = get_redis()
    if not redis_client:
        # Redis unavailable - fail open (allow the request)
        logger.warning(f"Redis unavailable, allowing anonymous analysis")
        return

    try:
        # Check device-based limits
        device_daily_key = _get_anonymous_device_key(device_id, "daily")
        device_monthly_key = _get_anonymous_device_key(device_id, "monthly")
        device_daily = int(redis_client.get(device_daily_key) or 0)
        device_monthly = int(redis_client.get(device_monthly_key) or 0)

        # Check IP-based limits
        ip_daily_key = _get_anonymous_ip_key(ip, "daily")
        ip_monthly_key = _get_anonymous_ip_key(ip, "monthly")
        ip_daily = int(redis_client.get(ip_daily_key) or 0)
        ip_monthly = int(redis_client.get(ip_monthly_key) or 0)

        # Check daily limit (blocked if EITHER exceeds)
        if device_daily >= limits["daily_analyses"] or ip_daily >= limits["daily_analyses"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily analysis limit reached ({limits['daily_analyses']} per day). "
                       f"Create an account for more analyses.",
                headers={"X-Tier-Limit-Type": "daily", "X-Tier": "anonymous"}
            )

        # Check monthly limit
        if device_monthly >= limits["monthly_analyses"] or ip_monthly >= limits["monthly_analyses"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Monthly analysis limit reached ({limits['monthly_analyses']} per month). "
                       f"Create an account for more analyses.",
                headers={"X-Tier-Limit-Type": "monthly", "X-Tier": "anonymous"}
            )

    except HTTPException:
        raise
    except Exception as e:
        # Redis error - fail open
        logger.error(f"Failed to check anonymous tier limits: {e}")


async def record_anonymous_analysis(device_id: str, ip: str) -> None:
    """Record an analysis usage for an anonymous user.

    Increments BOTH device_id and IP counters to prevent bypass.

    Args:
        device_id: Device identifier from localStorage
        ip: Client IP address
    """
    redis_client = get_redis()
    if not redis_client:
        logger.warning(f"Redis unavailable, cannot record anonymous analysis")
        return

    try:
        # Generate all keys
        device_daily_key = _get_anonymous_device_key(device_id, "daily")
        device_monthly_key = _get_anonymous_device_key(device_id, "monthly")
        ip_daily_key = _get_anonymous_ip_key(ip, "daily")
        ip_monthly_key = _get_anonymous_ip_key(ip, "monthly")

        # Use pipeline for atomic increment
        pipe = redis_client.pipeline()

        now = datetime.now(timezone.utc)

        # Device daily counter
        pipe.incr(device_daily_key)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_ttl = int((tomorrow - now).total_seconds())
        pipe.expire(device_daily_key, daily_ttl)

        # Device monthly counter
        pipe.incr(device_monthly_key)
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        monthly_ttl = int((next_month - now).total_seconds())
        pipe.expire(device_monthly_key, monthly_ttl)

        # IP daily counter
        pipe.incr(ip_daily_key)
        pipe.expire(ip_daily_key, daily_ttl)

        # IP monthly counter
        pipe.incr(ip_monthly_key)
        pipe.expire(ip_monthly_key, monthly_ttl)

        pipe.execute()

        logger.debug(f"Recorded anonymous analysis for device={device_id[:12]}... ip={ip}")

    except Exception as e:
        logger.error(f"Failed to record anonymous analysis: {e}")


# ========== Guest Creation Rate Limiting ==========
#
# Prevents "Clear Guest Data" abuse (creating new device_id repeatedly)
# Limit: 2 guest creations per day per IP
#   - 1st: Initial guest creation
#   - 2nd: One accidental reset/recreate allowed
#   - 3rd+: Blocked


def _get_guest_creation_key(ip: str) -> str:
    """Generate Redis key for guest creation rate limit.

    Args:
        ip: Client IP address

    Returns:
        Redis key like "tier:guest_create:ip:{ip}:2024-01-15"
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"tier:guest_create:ip:{ip}:{date_str}"


async def check_guest_creation_limit(ip: str) -> None:
    """Check if IP can create a new guest account.

    Limit: 2 guest creations per day per IP
    - Allows initial creation + one mistake/reset

    Args:
        ip: Client IP address

    Raises:
        HTTPException 429: If IP has exceeded daily guest creation limit
    """
    redis_client = get_redis()
    if not redis_client:
        # Redis unavailable - fail open
        logger.warning(f"Redis unavailable, allowing guest creation")
        return

    try:
        key = _get_guest_creation_key(ip)
        count = int(redis_client.get(key) or 0)

        if count >= 2:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You have reached the daily guest account limit. "
                       "Please create a registered account or try again tomorrow.",
                headers={"X-Tier-Limit-Type": "guest_creation"}
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check guest creation limit: {e}")


async def record_guest_creation(ip: str) -> None:
    """Record that a guest account was created from this IP.

    Args:
        ip: Client IP address
    """
    redis_client = get_redis()
    if not redis_client:
        logger.warning(f"Redis unavailable, cannot record guest creation")
        return

    try:
        key = _get_guest_creation_key(ip)
        now = datetime.now(timezone.utc)

        # Increment and set TTL to midnight
        redis_client.incr(key)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        ttl = int((tomorrow - now).total_seconds())
        redis_client.expire(key, ttl)

        logger.debug(f"Recorded guest creation for ip={ip}")

    except Exception as e:
        logger.error(f"Failed to record guest creation: {e}")
