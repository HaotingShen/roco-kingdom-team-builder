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
    GUEST_CREATION_LIMIT_PER_DAY,
    RETRY_GRACE_TTL,
    RETRY_GRACE_MAX_RETRIES,
)
from backend.logger import logger
from backend import models


# Localized rate limit messages
RATE_LIMIT_MESSAGES = {
    "en": {
        "daily_limit_anonymous": "Daily analysis limit reached ({limit} per day). Create an account for more analyses.",
        "monthly_limit_anonymous": "Monthly analysis limit reached ({limit} per month). Create an account for more analyses.",
        "daily_limit_unverified": "Daily analysis limit reached. Verify your email to unlock {free_limit} analyses per day.",
        "monthly_limit_unverified": "Monthly analysis limit reached. Verify your email to unlock more analyses.",
        "daily_limit_user": "Daily analysis limit reached ({limit} per day for current tier).",
        "monthly_limit_user": "Monthly analysis limit reached ({limit} per month for current tier).",
        "device_cap": "Analysis limit reached. Multiple accounts detected from this device.",
        "ip_cap": "Analysis limit reached. Please try again tomorrow.",
        "teams_limit_guest": "Team limit reached ({limit} teams for guests). Create an account to save more teams.",
        "teams_limit_unverified": "Team limit reached ({limit} teams). Verify your email to save up to {free_limit} teams.",
        "teams_limit_user": "Team limit reached ({limit} teams for current tier).",
    },
    "zh": {
        "daily_limit_anonymous": "已达到每日分析次数上限（每天 {limit} 次），创建账号可获得更多分析次数。",
        "monthly_limit_anonymous": "已达到每月分析次数上限（每月 {limit} 次），创建账号可获得更多分析次数。",
        "daily_limit_unverified": "已达到每日分析次数上限，验证邮箱后每天可获得 {free_limit} 次分析次数。",
        "monthly_limit_unverified": "已达到每月分析次数上限，验证邮箱后可获得更多分析次数。",
        "daily_limit_user": "已达到每日分析次数上限（目前等级每天 {limit} 次）。",
        "monthly_limit_user": "已达到每月分析次数上限（目前等级每月 {limit} 次）。",
        "device_cap": "已达到分析次数上限，检测到此设备有多个账号。",
        "ip_cap": "已达到分析次数上限，请明天再试。",
        "teams_limit_guest": "已达到队伍数量上限（访客最多 {limit} 支队伍），创建账号可保存更多队伍。",
        "teams_limit_unverified": "已达到队伍数量上限（{limit} 支），验证邮箱后最多可保存 {free_limit} 支队伍。",
        "teams_limit_user": "已达到队伍数量上限（目前等级最多 {limit} 支队伍）。",
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
    Get effective tier for a user, considering admin status and email verification.

    - Admins get 'unlimited' regardless of subscription_tier.
    - Registered users who have not verified their email are capped at 'guest'
      limits until they verify, then their actual subscription_tier applies.

    Args:
        user: User model instance

    Returns:
        Effective tier string
    """
    from backend.dependencies import is_admin_user

    if is_admin_user(user):
        return "unlimited"
    if not user.is_guest and not user.email_verified:
        return "guest"
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

        is_unverified = not user.is_guest and not user.email_verified

        # Check daily limit
        if daily_used >= limits["daily_analyses"]:
            if is_unverified:
                free_limit = get_tier_limits("free")["daily_analyses"]
                detail = get_rate_limit_message(
                    "daily_limit_unverified", lang,
                    limit=limits["daily_analyses"], free_limit=free_limit
                )
            else:
                detail = get_rate_limit_message(
                    "daily_limit_user", lang,
                    limit=limits["daily_analyses"], tier=tier
                )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers={"X-Tier-Limit-Type": "daily"}
            )

        # Check monthly limit
        if limits["monthly_analyses"] != -1 and monthly_used >= limits["monthly_analyses"]:
            if is_unverified:
                detail = get_rate_limit_message("monthly_limit_unverified", lang)
            else:
                detail = get_rate_limit_message(
                    "monthly_limit_user", lang,
                    limit=limits["monthly_analyses"], tier=tier
                )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
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


async def seed_user_counter_from_device(user: models.User, device_id: str) -> None:
    """Seed a new user's daily counter from the device's cross-account cap count.

    Called after creating a new guest or registered user account. Ensures the
    quota display is honest — if the device already has N analyses today (from
    anonymous or previous accounts), the new account starts at N instead of 0.

    Caps the seeded value at the tier's daily limit to avoid confusing over-limit
    displays (e.g., prevents showing 3/2 when device_count exceeds tier limit).
    Skips silently if device_id is unknown or Redis is unavailable (fail open).
    """
    if not device_id or device_id == "unknown-device":
        return

    redis_client = get_redis()
    if not redis_client:
        logger.warning(f"Redis unavailable, skipping counter seeding for user {user.id}")
        return

    try:
        device_key = _get_device_daily_key(device_id)
        device_count = int(redis_client.get(device_key) or 0)

        if device_count <= 0:
            return

        tier = get_effective_tier(user)
        limits = get_tier_limits(tier)
        daily_limit = limits["daily_analyses"]
        seed_count = device_count if daily_limit == -1 else min(device_count, daily_limit)

        if seed_count <= 0:
            return

        user_key = _get_user_key(user.id, "daily")
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        ttl = int((tomorrow - now).total_seconds())

        redis_client.set(user_key, seed_count, ex=ttl)
        logger.info(
            f"Seeded daily counter for user {user.id} ({tier}) "
            f"from device {device_id[:12]}...: {seed_count}/{daily_limit}"
        )

    except Exception as e:
        logger.error(f"Failed to seed counter for user {user.id}: {e}")


async def transfer_monthly_quota_from_guest(
    new_user: models.User, prior_guest_id: int, device_id: str
) -> None:
    """Transfer monthly quota counter from a prior guest account to a newly registered user.

    Called when a user registers after logging out of a guest account (Case 2 in register_user).
    Daily quota is handled separately by seed_user_counter_from_device, which reads the
    cross-account device cap. Monthly has no cross-account cap, so we reconstruct the total
    from two sources and sum them:
      - Guest monthly: tier:user:{prior_guest_id}:monthly:{YYYY-MM}
      - Anonymous device monthly: tier:anon:device:{device_id}:monthly:{YYYY-MM}

    These track distinct usage (guest analyses vs anonymous analyses), so summing them
    gives the correct total without double-counting.

    Caps the result at the new user's monthly limit. Fails open if Redis is unavailable.
    """
    redis_client = get_redis()
    if not redis_client:
        logger.warning(f"Redis unavailable, skipping monthly quota transfer for user {new_user.id}")
        return

    try:
        now = datetime.now(timezone.utc)
        month_str = now.strftime("%Y-%m")

        # Guest's own monthly usage
        guest_monthly_key = f"tier:user:{prior_guest_id}:monthly:{month_str}"
        guest_monthly = int(redis_client.get(guest_monthly_key) or 0)

        # Anonymous monthly usage on the same device (before guest account was created)
        anon_monthly = 0
        if device_id and device_id != "unknown-device":
            anon_monthly_key = _get_anonymous_device_key(device_id, "monthly")
            anon_monthly = int(redis_client.get(anon_monthly_key) or 0)

        total = guest_monthly + anon_monthly
        if total <= 0:
            return

        tier = get_effective_tier(new_user)
        limits = get_tier_limits(tier)
        monthly_limit = limits["monthly_analyses"]
        seed_count = total if monthly_limit == -1 else min(total, monthly_limit)

        if seed_count <= 0:
            return

        user_monthly_key = _get_user_key(new_user.id, "monthly")
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        ttl = int((next_month - now).total_seconds())

        redis_client.set(user_monthly_key, seed_count, ex=ttl)
        logger.info(
            f"Transferred monthly quota to user {new_user.id} ({tier}): "
            f"{seed_count}/{monthly_limit} (guest={guest_monthly}, anon={anon_monthly})"
        )

    except Exception as e:
        logger.error(f"Failed to transfer monthly quota for user {new_user.id}: {e}")


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
        if user.is_guest:
            message = get_rate_limit_message(
                "teams_limit_guest", lang,
                limit=limits["teams_limit"]
            )
        elif not user.email_verified:
            free_limit = get_tier_limits("free")["teams_limit"]
            message = get_rate_limit_message(
                "teams_limit_unverified", lang,
                limit=limits["teams_limit"], free_limit=free_limit
            )
        else:
            message = get_rate_limit_message(
                "teams_limit_user", lang,
                limit=limits["teams_limit"], tier=tier
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
            headers={"X-Tier-Limit-Type": "teams"}
        )


# ========== Device Owner Lookup ==========
#
# When an anonymous user's device_id maps to an existing guest or registered
# account, we use that account's quota instead of granting fresh anonymous quota.
# This prevents "double-dipping" by logging out to get extra analyses.


def find_device_owner(device_id: str, db: Session) -> Optional[models.User]:
    """Look up the account that owns this device_id.

    When a user logs out but their device_id cookie persists, we can find
    their account and apply its quota to anonymous requests from the same device.

    Priority: registered users over guests (guest may have been promoted).
    If multiple users share a device_id, the most recently active is returned.

    Args:
        device_id: Device identifier from httpOnly cookie
        db: Database session

    Returns:
        User model if found, None otherwise
    """
    if not device_id or device_id == "unknown-device":
        return None

    try:
        user = (
            db.query(models.User)
            .filter(
                models.User.device_id == device_id,
                models.User.is_active == True,
            )
            .order_by(
                models.User.is_guest.asc(),           # registered first
                models.User.last_active_at.desc().nullslast(),  # most recent guest activity
                models.User.last_login_at.desc().nullslast(),   # most recent registered login
            )
            .first()
        )
        if user:
            logger.debug(
                f"Device {device_id[:12]}... owned by user {user.id} "
                f"({user.subscription_tier} tier, guest={user.is_guest})"
            )
        return user
    except Exception as e:
        logger.error(f"Failed to look up device owner for {device_id[:12]}...: {e}")
        return None


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
# Limit: GUEST_CREATION_LIMIT_PER_DAY per IP (default 2)
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

        if count >= GUEST_CREATION_LIMIT_PER_DAY:
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


# ========== Retry Grace (partial analysis failure) ==========
#
# When an analysis partially succeeds (some LLM calls fail), quota is charged
# immediately. A grace window allows free retries so "Retry (Free)" is truthful.
#
# Grace key format: retry_grace:{user|device|ip}:{id}:{team_hash}:{language}
# Grace value: integer counter (starts at RETRY_GRACE_MAX_RETRIES, decremented on use)


def _get_retry_grace_key(
    identity_type: str,
    identity_value: str,
    team_hash: str,
    language: str,
) -> str:
    """Generate Redis key for retry grace marker.

    Args:
        identity_type: "user", "device", or "ip"
        identity_value: user ID, device ID, or IP address
        team_hash: Language-independent team composition hash
        language: Analysis language (included to prevent cross-language exploits)

    Returns:
        Redis key like "retry_grace:user:42:abc123:zh"
    """
    return f"retry_grace:{identity_type}:{identity_value}:{team_hash}:{language}"


def _resolve_grace_identity(
    effective_user: Optional[models.User],
    device_id: str,
    client_ip: str,
) -> tuple[str, str]:
    """Resolve the most-specific identity for grace key.

    Uses hierarchy: authenticated user > known device > IP (last resort).
    Only one identity is used to prevent shared-IP exploits.

    Returns:
        Tuple of (identity_type, identity_value)
    """
    if effective_user is not None:
        return ("user", str(effective_user.id))
    if device_id and device_id != "unknown-device":
        return ("device", device_id)
    return ("ip", client_ip)


async def set_retry_grace(
    effective_user: Optional[models.User],
    device_id: str,
    client_ip: str,
    team_hash: str,
    language: str,
) -> None:
    """Set retry grace marker after partial analysis success + quota charge.

    Called when: successful_calls > 0 AND NOT all_succeeded.
    Sets a counter-based grace marker for the most-specific identity.

    Args:
        effective_user: Authenticated user (or None for anonymous)
        device_id: Device identifier from cookie
        client_ip: Client IP address
        team_hash: Language-independent team composition hash
        language: Analysis language
    """
    redis_client = get_redis()
    if not redis_client:
        logger.warning("Redis unavailable, cannot set retry grace")
        return

    try:
        identity_type, identity_value = _resolve_grace_identity(
            effective_user, device_id, client_ip
        )
        key = _get_retry_grace_key(identity_type, identity_value, team_hash, language)
        redis_client.setex(key, RETRY_GRACE_TTL, RETRY_GRACE_MAX_RETRIES)
        logger.info(
            f"Set retry grace: {identity_type}={identity_value[:12]}... "
            f"team={team_hash[:12]}... lang={language} retries={RETRY_GRACE_MAX_RETRIES}"
        )
    except Exception as e:
        logger.error(f"Failed to set retry grace: {e}")


async def check_retry_grace(
    effective_user: Optional[models.User],
    device_id: str,
    client_ip: str,
    team_hash: str,
    language: str,
) -> bool:
    """Check if a retry grace marker exists for this analysis.

    Returns True if the most-specific identity has an active grace marker
    with remaining retries > 0. Returns False if Redis is unavailable
    (fail closed — no grace means normal quota checks apply).

    Args:
        effective_user: Authenticated user (or None for anonymous)
        device_id: Device identifier from cookie
        client_ip: Client IP address
        team_hash: Language-independent team composition hash
        language: Analysis language

    Returns:
        True if grace is active with retries remaining
    """
    redis_client = get_redis()
    if not redis_client:
        return False

    try:
        identity_type, identity_value = _resolve_grace_identity(
            effective_user, device_id, client_ip
        )
        key = _get_retry_grace_key(identity_type, identity_value, team_hash, language)
        value = redis_client.get(key)
        if value is not None and int(value) > 0:
            logger.info(f"Retry grace found: {key} (retries remaining: {value})")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to check retry grace: {e}")
        return False


async def consume_retry_grace(
    effective_user: Optional[models.User],
    device_id: str,
    client_ip: str,
    team_hash: str,
    language: str,
) -> bool:
    """Consume one retry from the grace counter.

    Atomically decrements the counter. Returns True if retry is allowed
    (counter was > 0 before decrement). If counter reaches 0, deletes the key.

    Args:
        effective_user: Authenticated user (or None for anonymous)
        device_id: Device identifier from cookie
        client_ip: Client IP address
        team_hash: Language-independent team composition hash
        language: Analysis language

    Returns:
        True if retry is allowed (counter was positive), False if exhausted
    """
    redis_client = get_redis()
    if not redis_client:
        return False

    try:
        identity_type, identity_value = _resolve_grace_identity(
            effective_user, device_id, client_ip
        )
        key = _get_retry_grace_key(identity_type, identity_value, team_hash, language)
        new_value = redis_client.decr(key)

        if new_value <= 0:
            # Grace exhausted — clean up
            redis_client.delete(key)
            logger.info(
                f"Retry grace exhausted: {identity_type}={identity_value[:12]}... "
                f"team={team_hash[:12]}... lang={language}"
            )
            return False

        logger.info(
            f"Retry grace consumed: {identity_type}={identity_value[:12]}... "
            f"team={team_hash[:12]}... lang={language} retries_remaining={new_value}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to consume retry grace: {e}")
        return False


async def clear_retry_grace(
    effective_user: Optional[models.User],
    device_id: str,
    client_ip: str,
    team_hash: str,
    language: str,
) -> None:
    """Clear retry grace marker (called on full success or from cached path).

    Args:
        effective_user: Authenticated user (or None for anonymous)
        device_id: Device identifier from cookie
        client_ip: Client IP address
        team_hash: Language-independent team composition hash
        language: Analysis language
    """
    redis_client = get_redis()
    if not redis_client:
        return

    try:
        identity_type, identity_value = _resolve_grace_identity(
            effective_user, device_id, client_ip
        )
        key = _get_retry_grace_key(identity_type, identity_value, team_hash, language)
        deleted = redis_client.delete(key)
        if deleted:
            logger.info(
                f"Cleared retry grace: {identity_type}={identity_value[:12]}... "
                f"team={team_hash[:12]}... lang={language}"
            )
    except Exception as e:
        logger.error(f"Failed to clear retry grace: {e}")


# TTL matches LLM cache TTL so user markers expire together with cached results
_USER_ANALYZED_TTL = 3600  # 1 hour


async def has_user_analyzed_team(
    effective_user: Optional[models.User],
    device_id: str,
    client_ip: str,
    team_hash: str,
    language: str,
) -> bool:
    """Check (EXISTS) whether this identity has already paid quota for this team + language.

    Used as a pre-quota-check gate in the cached path: if True, skip quota checks
    entirely so a user at their daily limit can still retrieve their own cached result.
    Fails open (returns False) on Redis error — quota checks will then run normally.
    """
    redis_client = get_redis()
    if not redis_client:
        return False
    try:
        identity_type, identity_value = _resolve_grace_identity(effective_user, device_id, client_ip)
        key = f"user_analyzed:{identity_type}:{identity_value}:{team_hash}:{language}"
        return redis_client.exists(key) > 0
    except Exception as e:
        logger.error(f"Failed to check user_analyzed: {e}")
        return False


async def try_claim_user_analysis_slot(
    effective_user: Optional[models.User],
    device_id: str,
    client_ip: str,
    team_hash: str,
    language: str,
) -> bool:
    """Atomically claim the analysis slot for this identity + team + language.

    Uses Redis SET NX EX to prevent concurrent double-charges on cached results:
    - Returns True if this request claimed the slot (will pay quota).
    - Returns False if slot was already claimed by a previous payment within the
      cache TTL window OR by a concurrent request from the same user — both cases
      mean no quota should be charged for this request.

    Fails open (returns True → pay) on Redis error so that quota is charged rather
    than silently given away.
    """
    redis_client = get_redis()
    if not redis_client:
        return True  # fail open: charge quota rather than give free result
    try:
        identity_type, identity_value = _resolve_grace_identity(effective_user, device_id, client_ip)
        key = f"user_analyzed:{identity_type}:{identity_value}:{team_hash}:{language}"
        # SET NX EX: atomic set-if-not-exists with TTL — returns None if key existed
        result = redis_client.set(key, 1, ex=_USER_ANALYZED_TTL, nx=True)
        claimed = result is not None
        if claimed:
            logger.debug(
                f"Claimed analysis slot: {identity_type}={identity_value[:12]}... "
                f"team={team_hash[:12]}... lang={language}"
            )
        else:
            logger.debug(
                f"Analysis slot already claimed (same user within TTL or concurrent duplicate): "
                f"{identity_type}={identity_value[:12]}... team={team_hash[:12]}... lang={language}"
            )
        return claimed
    except Exception as e:
        logger.error(f"Failed to claim analysis slot: {e}")
        return True  # fail open: charge quota


async def mark_user_team_analyzed(
    effective_user: Optional[models.User],
    device_id: str,
    client_ip: str,
    team_hash: str,
    language: str,
) -> None:
    """Unconditionally set the user-analyzed marker after actual LLM quota was charged.

    Used in the non-cached path after successful quota charge so that subsequent
    cached-path requests from the same user within the TTL window are free.
    Uses plain SET (not NX) to ensure the marker is always written even if a
    previous partial result had already set it.
    """
    redis_client = get_redis()
    if not redis_client:
        return
    try:
        identity_type, identity_value = _resolve_grace_identity(effective_user, device_id, client_ip)
        key = f"user_analyzed:{identity_type}:{identity_value}:{team_hash}:{language}"
        redis_client.set(key, 1, ex=_USER_ANALYZED_TTL)
        logger.debug(
            f"Marked user_analyzed: {identity_type}={identity_value[:12]}... "
            f"team={team_hash[:12]}... lang={language}"
        )
    except Exception as e:
        logger.error(f"Failed to mark user_analyzed: {e}")
