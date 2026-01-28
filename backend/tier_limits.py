"""Tier-based analysis limits (Phase 7A).

Tracks and enforces analysis limits based on user subscription tier.

Features:
- Daily and monthly analysis limits per tier
- Team count limits
- Cross-account daily caps (device + IP) to prevent multi-account abuse
- Redis-backed usage tracking with automatic TTL
- Graceful degradation (allows on Redis failure)

Usage:
    from backend.tier_limits import (
        check_analysis_limit,
        record_analysis_usage,
        check_device_daily_cap,
        check_ip_daily_cap,
        record_device_and_ip_usage,
    )

    # In analysis endpoint:
    await check_analysis_limit(user, db)  # Per-user limit
    await check_device_daily_cap(device_id, user)  # Cross-account device limit
    await check_ip_daily_cap(ip, user)  # IP fallback limit
    # ... perform analysis ...
    await record_analysis_usage(user)  # Increment user counters
    await record_device_and_ip_usage(device_id, ip)  # Increment device/IP counters
"""

import redis
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from backend.config import (
    TIER_LIMITS,
    REDIS_URL,
    DEVICE_DAILY_ANALYSIS_CAP,
    IP_DAILY_ANALYSIS_CAP,
)
from backend.logger import logger
from backend import models


# Localized rate limit messages
RATE_LIMIT_MESSAGES = {
    "en": {
        "daily_limit_anonymous": "Daily analysis limit reached ({limit} per day). Create an account for more analyses.",
        "monthly_limit_anonymous": "Monthly analysis limit reached ({limit} per month). Create an account for more analyses.",
        "daily_limit_user": "Daily analysis limit reached ({limit} per day for {tier} tier). Upgrade to premium for more analyses.",
        "monthly_limit_user": "Monthly analysis limit reached ({limit} per month for {tier} tier). Upgrade to premium for more analyses.",
        "device_cap": "Analysis limit reached. Multiple accounts detected from this device.",
        "ip_cap": "Analysis limit reached. Please try again tomorrow.",
        "teams_limit_guest": "Team limit reached ({limit} teams for guests). Create an account to save more teams.",
        "teams_limit_user": "Team limit reached ({limit} teams for {tier} tier). Delete some teams or upgrade for more.",
    },
    "zh": {
        "daily_limit_anonymous": "已达到每日分析上限（每天 {limit} 次）。创建账号可获得更多分析次数。",
        "monthly_limit_anonymous": "已达到每月分析上限（每月 {limit} 次）。创建账号可获得更多分析次数。",
        "daily_limit_user": "已达到每日分析上限（{tier} 等级每天 {limit} 次）。升级至高级版可获得更多分析次数。",
        "monthly_limit_user": "已达到每月分析上限（{tier} 等级每月 {limit} 次）。升级至高级版可获得更多分析次数。",
        "device_cap": "已达到分析上限。检测到此设备有多个账号。",
        "ip_cap": "已达到分析上限。请明天再试。",
        "teams_limit_guest": "已达到队伍数量上限（访客最多 {limit} 支队伍）。创建账号可保存更多队伍。",
        "teams_limit_user": "已达到队伍数量上限（{tier} 等级最多 {limit} 支队伍）。删除部分队伍或升级以获得更多。",
    },
}


def get_rate_limit_message(key: str, lang: str = "en", **kwargs) -> str:
    """Get localized rate limit message.

    Args:
        key: Message key
        lang: Language code ("en" or "zh")
        **kwargs: Format arguments

    Returns:
        Localized message with arguments formatted
    """
    messages = RATE_LIMIT_MESSAGES.get(lang, RATE_LIMIT_MESSAGES["en"])
    template = messages.get(key, RATE_LIMIT_MESSAGES["en"].get(key, key))
    return template.format(**kwargs)


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


async def check_analysis_limit(user: models.User, db: Session, lang: str = "en") -> None:
    """Check if user is within their analysis limits.

    Args:
        user: User model instance
        db: Database session
        lang: Language code for error messages ("en" or "zh")

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
                detail=get_rate_limit_message(
                    "daily_limit_user",
                    lang,
                    limit=limits["daily_analyses"],
                    tier=tier
                ),
                headers={"X-Tier-Limit-Type": "daily"}
            )

        # Check monthly limit
        if limits["monthly_analyses"] != -1 and monthly_used >= limits["monthly_analyses"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=get_rate_limit_message(
                    "monthly_limit_user",
                    lang,
                    limit=limits["monthly_analyses"],
                    tier=tier
                ),
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


async def check_teams_limit(user: models.User, db: Session, lang: str = "en") -> None:
    """Check if user can create more teams.

    Args:
        user: User model instance
        db: Database session
        lang: Language code for error messages ("en" or "zh")

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
        # Use different message for guest vs registered users
        if user.is_guest:
            message = get_rate_limit_message(
                "teams_limit_guest",
                lang,
                limit=limits["teams_limit"]
            )
        else:
            message = get_rate_limit_message(
                "teams_limit_user",
                lang,
                limit=limits["teams_limit"],
                tier=tier
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
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


async def check_anonymous_analysis_limit(device_id: str, ip: str, lang: str = "en") -> None:
    """Check if anonymous user is within their analysis limits.

    Uses dual-key tracking (device_id AND IP) to prevent abuse.
    User is blocked if EITHER device_id OR IP has hit the limit.

    Args:
        device_id: Device identifier from localStorage
        ip: Client IP address
        lang: Language code for error messages ("en" or "zh")

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
                detail=get_rate_limit_message(
                    "daily_limit_anonymous",
                    lang,
                    limit=limits["daily_analyses"]
                ),
                headers={"X-Tier-Limit-Type": "daily", "X-Tier": "anonymous"}
            )

        # Check monthly limit
        if device_monthly >= limits["monthly_analyses"] or ip_monthly >= limits["monthly_analyses"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=get_rate_limit_message(
                    "monthly_limit_anonymous",
                    lang,
                    limit=limits["monthly_analyses"]
                ),
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


# ========== Cross-Account Daily Caps ==========
#
# Prevents multi-account abuse on the same device/IP.
# Even with multiple accounts, users share a combined daily analysis budget.
#
# Device cap: Primary (httpOnly cookie, hard to tamper)
# IP cap: Fallback when device_id missing, also catches VPN abuse
#
# Premium/unlimited users are EXEMPT from these caps.


def _get_device_daily_key(device_id: str) -> str:
    """Generate Redis key for device daily cap.

    Args:
        device_id: Device identifier from httpOnly cookie

    Returns:
        Redis key like "tier:device:{device_id}:daily:2024-01-15"
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"tier:device:{device_id}:daily:{date_str}"


def _get_ip_daily_key(ip: str) -> str:
    """Generate Redis key for IP daily cap.

    Args:
        ip: Client IP address

    Returns:
        Redis key like "tier:ip:{ip}:daily:2024-01-15"
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"tier:ip:{ip}:daily:{date_str}"


def _is_exempt_from_device_cap(user: Optional[models.User]) -> bool:
    """Check if user is exempt from device/IP daily caps.

    Premium and unlimited tier users are exempt because:
    - They're paying customers (shouldn't be penalized)
    - Multi-account abuse is less of a concern for paying users

    Args:
        user: User model instance, or None for anonymous

    Returns:
        True if exempt from device/IP caps
    """
    if user is None:
        return False

    tier = get_effective_tier(user)
    return tier in ("premium", "unlimited")


async def check_device_daily_cap(device_id: str, user: Optional[models.User] = None) -> None:
    """Check if device has exceeded daily analysis cap.

    This is a CROSS-ACCOUNT limit - all accounts on the same device
    share this budget. Prevents multi-account abuse.

    Args:
        device_id: Device identifier from httpOnly cookie
        user: Current user (to check exemption)

    Raises:
        HTTPException 429: If device has exceeded daily cap
    """
    # Premium/unlimited users are exempt
    if _is_exempt_from_device_cap(user):
        return

    # Skip for unknown devices
    if device_id == "unknown-device":
        return

    redis_client = get_redis()
    if not redis_client:
        # Redis unavailable - fail open
        logger.warning(f"Redis unavailable, skipping device daily cap check")
        return

    try:
        key = _get_device_daily_key(device_id)
        count = int(redis_client.get(key) or 0)

        if count >= DEVICE_DAILY_ANALYSIS_CAP:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily device limit reached ({DEVICE_DAILY_ANALYSIS_CAP} analyses per day). "
                       f"This limit applies across all accounts on this device. "
                       f"Try again tomorrow or upgrade to premium.",
                headers={"X-Tier-Limit-Type": "device_daily"}
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check device daily cap: {e}")


async def check_ip_daily_cap(ip: str, user: Optional[models.User] = None) -> None:
    """Check if IP has exceeded daily analysis cap.

    This is a FALLBACK limit when device_id is not available.
    Also serves as an abuse signal for VPN users trying to bypass device limits.

    Args:
        ip: Client IP address
        user: Current user (to check exemption)

    Raises:
        HTTPException 429: If IP has exceeded daily cap
    """
    # Premium/unlimited users are exempt
    if _is_exempt_from_device_cap(user):
        return

    redis_client = get_redis()
    if not redis_client:
        # Redis unavailable - fail open
        logger.warning(f"Redis unavailable, skipping IP daily cap check")
        return

    try:
        key = _get_ip_daily_key(ip)
        count = int(redis_client.get(key) or 0)

        if count >= IP_DAILY_ANALYSIS_CAP:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily IP limit reached ({IP_DAILY_ANALYSIS_CAP} analyses per day). "
                       f"This limit helps prevent abuse. "
                       f"Try again tomorrow or upgrade to premium.",
                headers={"X-Tier-Limit-Type": "ip_daily"}
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check IP daily cap: {e}")


async def record_device_and_ip_usage(device_id: str, ip: str) -> None:
    """Record analysis usage for device and IP daily caps.

    Should be called AFTER successful analysis completion.
    Increments both device and IP counters.

    Args:
        device_id: Device identifier from httpOnly cookie
        ip: Client IP address
    """
    redis_client = get_redis()
    if not redis_client:
        logger.warning(f"Redis unavailable, cannot record device/IP usage")
        return

    try:
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        ttl = int((tomorrow - now).total_seconds())

        pipe = redis_client.pipeline()

        # Record device usage (skip for unknown devices)
        if device_id != "unknown-device":
            device_key = _get_device_daily_key(device_id)
            pipe.incr(device_key)
            pipe.expire(device_key, ttl)

        # Always record IP usage
        ip_key = _get_ip_daily_key(ip)
        pipe.incr(ip_key)
        pipe.expire(ip_key, ttl)

        pipe.execute()

        logger.debug(f"Recorded device/IP usage: device={device_id[:12]}... ip={ip}")

    except Exception as e:
        logger.error(f"Failed to record device/IP usage: {e}")
