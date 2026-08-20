from fastapi import FastAPI, Depends, Query, HTTPException, status, Request, Response, Cookie, Body
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, cast, String, func, text
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from backend.config import (
    LLM_PROVIDER,
    ALLOWED_ORIGINS,
    LOG_LEVEL,
    ENABLE_REFERENCE_RESOLUTION,
    ENVIRONMENT,
    REDIS_URL,
    REDIS_CACHE_TTL,
    REDIS_LOCK_TIMEOUT,
    REDIS_LOCK_BLOCKING_TIMEOUT,
    COOKIE_DOMAIN,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    REFRESH_TOKEN_EXPIRE_DAYS,
    DEVICE_ID_COOKIE_MAX_AGE,
    ADMIN_EMAILS,
)
from backend.database import get_db, SessionLocal
from typing import Optional, List, Literal
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from backend import models, schemas
from backend.cache import llm_cache, RedisCache, redis_cache
from backend.rate_limiter import (
    limiter,
    rate_limit_exceeded_handler,
    check_analysis_rate_limit_async,
    record_analysis_async,
    clear_analysis_rate_limit_async,
    get_rate_limit_message,
    get_real_client_ip,
)
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from collections import Counter
from dataclasses import dataclass
import re
import asyncio
import json
import time
import secrets
import logging
import hashlib
import uuid
import jwt
from email_validator import validate_email, EmailNotValidError
from backend.llm_service import generate_analysis_json
from backend import reference_resolver
from backend.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_guest_username,
    generate_guest_display_id,
    generate_verification_token,
)
from backend.dependencies import (
    get_current_user,
    get_optional_user,
    require_registered_user,
    require_admin,
    is_admin_user,
    get_user_team,
    get_user_or_anonymous,
    get_device_id,
)
from backend.token_revocation import revocation_service
from backend.captcha import verify_captcha, get_captcha_config
from backend.tier_limits import (
    check_analysis_limit,
    record_analysis_usage,
    check_teams_limit,
    get_usage_stats,
    get_anonymous_usage_stats,
    check_anonymous_analysis_limit,
    record_anonymous_analysis,
    check_guest_creation_limit,
    record_guest_creation,
    check_device_daily_cap,
    check_ip_daily_cap,
    record_device_and_ip_usage,
    find_device_owner,
    set_retry_grace,
    check_retry_grace,
    consume_retry_grace,
    clear_retry_grace,
    has_user_analyzed_team,
    try_claim_user_analysis_slot,
    mark_user_team_analyzed,
    seed_user_counter_from_device,
    transfer_monthly_quota_from_guest,
    is_circuit_open,
    record_llm_failures,
    reset_llm_failure_counter,
    try_begin_analysis_inflight,
    end_analysis_inflight,
)
from backend.email_service import (
    send_verification_email,
    send_password_reset_email,
    send_email_change_verification,
    send_email,
)
from backend.username_validator import get_canonical_username, trim_username

# Setup logger
logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

# Battle Mechanics System Prompts
BATTLE_MECHANICS_ZH = """每位玩家携带6只精灵对战，每只精灵有6项属性（生命、物攻、魔攻、物防、魔防、速度）。实战中每只精灵只能携带4个技能。技能描述中的"攻击"或"双攻"同时影响物攻与魔攻；"防御"或"双防"同时影响物防与魔防。

战斗开始时双方各有4点魔力值，场上各只能同时上场1只精灵。精灵力竭（被击败）时失去1点魔力值（部分特性会改变此规则）。魔力值归零则判负。力竭后需手动选择新精灵入场。

每只精灵初始10点能量（部分特性影响初始值）。能量按精灵单独记录，释放技能消耗对应能量。

每回合双方同时选择一个行动：（1）释放技能：从4个技能中选1个并支付能量；（2）聚能：本回合不行动，恢复5点能量（属于状态类技能）；（3）主动更换精灵。血脉魔法不属于行动选项：若本回合可用，可在任意时点额外使用，不消耗行动或能量，并在己方行动前生效。

主动更换精灵先于所有技能结算。精灵主动入场时，若其携带含有"迅捷"效果的技能且能量充足，会立即自动释放首个满足条件的迅捷技能（按技能栏顺序）。迅捷仅在主动换上时触发，被动入场不触发。

所有技能分为三类：攻击类（物攻/魔攻）、防御类、状态类。存在"应对"系统：若敌方技能类别与本技能可应对类别匹配，则应对成功，本技能以最高优先级立即释放，忽略速度顺序。双方不可同时应对成功。未触发应对时按先手值判定顺序，先手值相同则速度高者先行动。主动更换始终优先于技能结算。

应对关系：防御类技能自带应对攻击；部分状态类技能带应对防御；部分攻击类技能带应对状态。这形成克制三角，预测对手技能类别选择应对是PvP关键策略。

增益指提升攻击、防御、速度、技能威力、连击数、吸血或降低技能能耗；减益相反。技能中的"全技能威力/全技能能耗"影响该精灵当前所有技能。精灵离场时清除非永久性增减益和大多数状态效果（印记除外）。

层数定义：当"层数"用于增益/减益时，以10为换算基准。百分比增减：每10% = 1层，如物攻+150% = +15层物攻。数值增减（非百分比且为10的倍数）：每10点 = 1层，如技能威力+20 = +2层技能威力。当"层数"用于状态/印记时，层数按状态本身叠加规则计算，不做上述换算。

冷却定义：技能或血脉魔法在再次使用前必须经过的回合数。除非另有说明，所有防御类技能的冷却为1回合，而其他类别的技能通常没有冷却；血脉魔法中"愿力强化"的冷却为3回合且每场战斗最多使用2次，而其他血脉魔法为每场一次性使用。

在进行队伍与精灵分析时，请默认对战结算遵循以上关于魔力值、力竭、能量、技能类别、应对系统、增减益、迅捷、先手与速度、层数定义、冷却定义及血脉魔法的规则。"""

BATTLE_MECHANICS_EN = """Each player brings 6 jinglings into battle. Each jingling has 6 stats (HP, Physical Attack, Magic Attack, Physical Defense, Magic Defense, Speed). In battle, each jingling can only carry 4 moves. In move descriptions, "Attack" affects both Physical and Magic Attack; "Defense" affects both Physical and Magic Defense.

At battle start, each player has 4 Life Points. Only 1 jingling per side can be on the field at once. When a jingling is defeated, the player loses 1 Life Point (some traits alter this). When Life Points reach 0, that player loses. After defeat, manually select a new jingling to enter.

Each jingling starts with 10 energy (some traits affect initial energy). Energy is tracked per jingling. Using moves consumes their marked energy cost.

Each turn, both players simultaneously choose one action: (1) Use a move: select 1 of 4 moves and pay its energy cost; (2) Focus: skip this turn, restore 5 energy (classified as Status-type move); (3) Actively switch jinglings. Magic Item does not count as an action. If available this turn, it may be used at any time without consuming an action or energy, and it takes effect before your chosen action resolves.

Active switching executes before all move resolutions. When a jingling enters via active switch, if it has any move with "Quick Entry" effect and enough energy to use it, it immediately and automatically uses the first eligible Quick Entry move in moveset slot order. Quick Entry only triggers on active switch-in, not passive entry.

All moves fall into three categories: Attack-type (Physical/Magic Attack), Defense-type, Status-type. A "Counter" system exists: if the opponent's move category matches this move's counterable category, counter succeeds and this move resolves immediately with highest priority, ignoring speed order. Both sides cannot counter simultaneously. Without counter triggers, turn order is determined by priority value; if equal, higher speed acts first. Active switching always executes before move resolution.

Counter relationships: All Defense moves have Counter Attack; some Status moves have Counter Defense; some Attack moves have Counter Status. This forms a counter triangle—predicting opponent's move category to select counters is key PvP strategy.

Buffs increase Attack, Defense, Speed, move power, Combo count, Lifesteal, or decrease move energy cost; Debuffs do the opposite. "All Move Power/Move Energy Cost" affects all moves currently carried by that jingling. When jinglings leave the field, non-permanent buffs/debuffs and most of status effects are removed (except marks).

Stack definition: When "stacks" are used for buffs/debuffs, convert using 10 as the base unit. For percentage changes, every 10% = 1 stack (e.g., Physical Attack +150% = +15 stacks of Physical Attack). For flat value changes (non-percentage and a multiple of 10), every 10 points = 1 stack (e.g., Move Power +20 = +2 stacks of Move Power). When "stacks" refer to status/mark effects, stacks follow their own stacking rules and do not use the above conversion.

Cooldown definition: The number of turns that must pass before a move or magic item can be used again. Unless otherwise specified, all Defense-type moves have a 1-turn cooldown, while moves of other categories have no cooldown. For magic items, "Willpower Enhancement" has a 3-turn cooldown and can be used at most 2 times per battle, while other magic item effects are single-use per battle.

When performing jingling and team analysis, assume battle resolution follows the above rules regarding Life Points, defeated state, energy, move categories, counter system, buffs/debuffs, Quick Entry, priority and speed, stack definitions, cooldown definitions, and Magic Items."""

app = FastAPI()


# CRITICAL: Trailing slash normalization middleware
class StripTrailingSlashMiddleware(BaseHTTPMiddleware):
    """
    Redirect trailing slashes to non-trailing for consistency.

    Examples:
    - /auth/register/ → /auth/register (307 redirect)
    - /teams/ → /teams (307 redirect)
    - / → / (root unchanged)

    This prevents duplicate endpoint issues and ensures
    frontend and backend routing is consistent.
    """
    async def dispatch(self, request: Request, call_next):
        if request.url.path != "/" and request.url.path.endswith("/"):
            # Remove trailing slash
            url = request.url.replace(path=request.url.path.rstrip("/"))
            return RedirectResponse(url=str(url), status_code=307)
        return await call_next(request)


app.add_middleware(StripTrailingSlashMiddleware)


# Device ID Cookie Middleware
DEVICE_ID_COOKIE_NAME = "device_id"

class DeviceIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to set/read device_id via httpOnly cookie.

    Why cookie over localStorage:
    - httpOnly: JavaScript cannot read/modify (XSS protection)
    - Server-controlled: Cannot be faked by client
    - Automatic: Sent with every request (no custom header needed)
    - Persistent: Survives until expiry (harder to clear selectively)

    Flow:
    1. Check for existing device_id cookie
    2. If missing, generate new UUID and set cookie
    3. Store device_id in request.state for endpoint access
    """
    async def dispatch(self, request: Request, call_next):
        device_id = request.cookies.get(DEVICE_ID_COOKIE_NAME)
        needs_cookie = False

        if not device_id:
            # Generate new device_id
            device_id = str(uuid.uuid4())
            needs_cookie = True
            logger.debug(f"Generated new device_id: {device_id[:12]}...")

        # Store in request state for access in endpoints
        request.state.device_id = device_id

        # Process request
        response = await call_next(request)

        # Set cookie if new device_id was generated
        if needs_cookie:
            response.set_cookie(
                key=DEVICE_ID_COOKIE_NAME,
                value=device_id,
                max_age=DEVICE_ID_COOKIE_MAX_AGE,
                httponly=True,
                samesite=COOKIE_SAMESITE,
                secure=COOKIE_SECURE,
                domain=COOKIE_DOMAIN,
                path="/",
            )

        return response


app.add_middleware(DeviceIDMiddleware)


# Log LLM provider on startup
logger.info(f"Using LLM provider: {LLM_PROVIDER}")

# The shared Redis cache singleton now lives in backend.cache (imported above)
# so the analysis package and main.py reference the same instance. Its
# connect()/disconnect() lifecycle is still driven by the startup/shutdown
# events below.


async def _periodic_prompt_log_cleanup():
    """Background task: delete prompt logs older than 7 days, runs every 24 hours."""
    while True:
        await asyncio.sleep(24 * 60 * 60)
        try:
            from backend.prompt_logger import clear_old_logs
            deleted = clear_old_logs(days=30)
            if deleted:
                logger.info(f"Prompt log cleanup: deleted {deleted} files older than 30 days")
        except Exception as e:
            logger.error(f"Prompt log cleanup failed: {e}")


async def _periodic_guest_cleanup():
    """
    Background task: delete orphaned and abandoned guest accounts, runs every 24 hours.

    Removes two categories:
    - Explicitly orphaned guests: is_active=False (set by reset-device-id)
    - Abandoned guests: active but no activity for 30+ days

    Uses a Redis distributed lock so only one uvicorn worker runs this
    (production runs --workers 2; without the lock both workers would delete
    the same rows concurrently).
    """
    await asyncio.sleep(60)  # Brief delay after startup before first run
    while True:
        try:
            # Acquire a short-lived Redis lock (non-blocking) so only one worker
            # runs per cycle. The lock TTL (3600s) expires well before the next
            # 24-hour cycle, so the other worker can win next time.
            lock = None
            acquired = True  # Default to running if Redis is unavailable
            if redis_cache._connected and redis_cache._redis:
                lock = redis_cache._redis.lock(
                    "cleanup:guests",
                    timeout=3600,
                    blocking_timeout=0,
                )
                acquired = await lock.acquire(blocking=False)

            if not acquired:
                logger.debug("Guest cleanup skipped: another worker already claimed this cycle")
            else:
                try:
                    db = SessionLocal()
                    try:
                        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

                        # Category 1: explicitly orphaned (reset-device-id was called)
                        # Category 2: abandoned — no activity for 30+ days
                        #   (use created_at as fallback when last_active_at is NULL)
                        guests_to_delete = db.query(models.User).filter(
                            models.User.is_guest == True,
                            or_(
                                models.User.is_active == False,
                                models.User.last_active_at < cutoff,
                                and_(
                                    models.User.last_active_at == None,
                                    models.User.created_at < cutoff,
                                ),
                            )
                        ).all()

                        count = len(guests_to_delete)
                        for guest in guests_to_delete:
                            db.delete(guest)
                        db.commit()

                        if count:
                            logger.info(f"Guest cleanup: deleted {count} orphaned/abandoned guest accounts")
                    finally:
                        db.close()
                finally:
                    if lock:
                        try:
                            if await lock.owned():
                                await lock.release()
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"Guest cleanup failed: {e}")
        await asyncio.sleep(24 * 60 * 60)


@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    logger.info("Application startup: connecting to Redis...")
    await redis_cache.connect()
    await revocation_service.connect()
    asyncio.create_task(_periodic_prompt_log_cleanup())
    asyncio.create_task(_periodic_guest_cleanup())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    logger.info("Application shutdown: disconnecting from Redis...")
    await redis_cache.disconnect()
    await revocation_service.disconnect()

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Add SlowAPI middleware for rate limiting
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Analysis routes ===
# The team-analysis system (analyze / analyze_by_id / saved-analysis CRUD) and
# all its helpers were extracted into the backend.analysis package. Registering
# the router here preserves the exact same public paths and behavior.
# See docs/analysis-system.md for the module map.
from backend.analysis.routes import router as analysis_router
app.include_router(analysis_router)

# Backward-compatible re-exports: these analysis helpers moved into the
# backend.analysis package but are imported from backend.main by the test suite
# (and possibly other callers). Re-exporting keeps those imports working.
from backend.analysis.computations import compute_effective_stats, compute_type_coverage
from backend.analysis.cache_keys import generate_team_cache_key, generate_team_composition_hash
from backend.analysis.service import _perform_team_analysis  # noqa: F401

# === TOP-LEVEL HELPER FUNCTIONS ===

def user_to_user_out(user: models.User) -> schemas.UserOut:
    """
    Convert a User model to UserOut schema with computed is_admin field.

    is_admin is computed from ADMIN_EMAILS env var, not stored in database.
    """
    return schemas.UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        is_guest=user.is_guest,
        email_verified=user.email_verified,
        subscription_tier=user.subscription_tier,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        is_admin=is_admin_user(user),
        guest_display_id=user.guest_display_id,
        preferred_language=user.preferred_language
    )



# ========== AUTH HELPER FUNCTIONS ==========

def set_refresh_token_cookie(response: Response, refresh_token: str):
    """
    Set refresh token as httpOnly cookie with security flags.

    SECURITY CONFIGURATION (based on deployment topology):

    SAME-SITE (recommended):
    - SameSite=Lax (CSRF protection built-in)
    - Domain=.yourdomain.com (shares across subdomains)
    - No CSRF tokens needed

    CROSS-SITE:
    - SameSite=None; Secure (requires CSRF tokens)
    - Domain=None (no shared domain)
    - Must validate CSRF token in requests
    """
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,           # JavaScript cannot access (XSS protection)
        secure=COOKIE_SECURE,    # HTTPS only in production
        samesite=COOKIE_SAMESITE,  # "lax" (same-site) or "none" (cross-site)
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 7 days
        path="/",                # Available to entire app
        domain=COOKIE_DOMAIN,    # ".yourdomain.com" or None
    )


def clear_refresh_token_cookie(response: Response):
    """Clear refresh token cookie on logout."""
    response.delete_cookie(
        key="refresh_token",
        path="/",
        domain=COOKIE_DOMAIN,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )


# ========== AUTH ENDPOINTS ==========

@app.post("/auth/guest", response_model=schemas.AuthResponse, tags=["Authentication"])
async def create_guest_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Create or retrieve guest user by device ID.

    SECURITY:
    - Device ID obtained from httpOnly cookie (set by middleware)
    - Prevents guest explosion from multiple tabs/refreshes (device_id deduplication)
    - Rate limited: 1 NEW guest per day per IP (prevents Clear Guest Data abuse)
    - Returning existing guest by device_id is NOT rate limited

    Flow:
    1. Frontend explicitly calls this when user clicks "Continue as Guest"
    2. Backend gets device_id from httpOnly cookie
    3. If guest with this device_id exists: Return existing guest
    4. If no: Check rate limit, then create new guest

    Note: This is only called when user explicitly chooses to be a guest.
    Anonymous users (no account) don't call this endpoint.
    """
    # Get device_id from httpOnly cookie (set by DeviceIDMiddleware)
    device_id = getattr(request.state, 'device_id', None)
    client_ip = get_real_client_ip(request)

    # Try to find existing guest by device_id
    if device_id:
        username = f"guest_{device_id[:12]}"
        existing_guest = db.query(models.User).filter(
            models.User.username == username,
            models.User.is_guest == True,
            models.User.is_active == True,
        ).first()

        if existing_guest:
            # Return existing guest (deduplication) - NOT rate limited
            # Update last_active_at for guest expiry tracking
            existing_guest.last_active_at = datetime.now(timezone.utc)
            db.commit()

            access_token = create_access_token(
                existing_guest.id,
                existing_guest.username,
                True,
                existing_guest.token_version
            )
            refresh_token = create_refresh_token(
                existing_guest.id,
                existing_guest.token_version
            )
            set_refresh_token_cookie(response, refresh_token)

            logger.info(f"Returned existing guest: {existing_guest.username} (ID={existing_guest.id})")

            return schemas.AuthResponse(
                access_token=access_token,
                token_type="bearer",
                user=user_to_user_out(existing_guest),
                is_returning_guest=True
            )

    # Creating NEW guest - check rate limit (1/day per IP)
    await check_guest_creation_limit(client_ip)

    # Create new guest with "guest" tier (not "free")
    username = f"guest_{device_id[:12]}" if device_id else generate_guest_username()

    # Clean up any inactive/deactivated guest with the same username so the unique constraint
    # doesn't block the INSERT (e.g. after "clear guest data" or registration with same device)
    if device_id:
        stale_guest = db.query(models.User).filter(
            models.User.username == username,
            models.User.is_guest == True,
            models.User.is_active == False,
        ).first()
        if stale_guest:
            db.delete(stale_guest)
            db.commit()
            logger.info(f"Removed stale inactive guest '{username}' (ID={stale_guest.id}) to allow re-creation")

    # Generate unique display ID (retry on collision)
    max_attempts = 10
    display_id = None
    for _ in range(max_attempts):
        candidate = generate_guest_display_id()
        existing = db.query(models.User).filter(
            models.User.guest_display_id == candidate
        ).first()
        if not existing:
            display_id = candidate
            break

    if not display_id:
        logger.error("Failed to generate unique guest display ID after max attempts")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create guest account. Please try again."
        )

    guest = models.User(
        username=username,
        canonical_username=username.lower(),  # Guest usernames are already safe
        guest_display_id=display_id,  # Unique 4-char ID for display (e.g., "A2B3")
        email=None,
        hashed_password=None,
        is_guest=True,
        is_active=True,
        token_version=0,
        subscription_tier="guest",  # Guest tier: 3/day analyses, 3 teams max
        device_id=device_id,  # Store device_id for tracking
        last_active_at=datetime.now(timezone.utc),  # For guest expiry
    )

    db.add(guest)
    try:
        db.commit()
    except IntegrityError:
        # Two simultaneous first visits from the same device (double-click /
        # two tabs) both pass the existence check and race on the unique
        # username; the loser adopts the winner's guest account instead of 500ing.
        db.rollback()
        guest = db.query(models.User).filter(
            models.User.username == username,
            models.User.is_guest == True,
            models.User.is_active == True,
        ).first()
        if not guest:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create guest account. Please try again."
            )
    db.refresh(guest)

    # Seed daily counter from device usage so quota display is honest
    await seed_user_counter_from_device(guest, device_id)

    # Record guest creation for rate limiting
    await record_guest_creation(client_ip)

    # Generate tokens
    access_token = create_access_token(guest.id, guest.username, True, guest.token_version)
    refresh_token = create_refresh_token(guest.id, guest.token_version)
    set_refresh_token_cookie(response, refresh_token)

    logger.info(f"Created new guest: {guest.username} (ID={guest.id}) from IP {client_ip}")

    return schemas.AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_to_user_out(guest),
        is_returning_guest=False
    )


@app.post("/auth/register", tags=["Authentication"])
@limiter.limit("3/hour")  # SECURITY: Prevent bot signups
async def register_user(
    request: Request,
    response: Response,
    user_data: schemas.UserRegister,
    current_user: Optional[models.User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Register a new user OR convert guest to registered user.

    SECURITY:
    - Rate limited (3 registrations per hour per IP)
    - CAPTCHA verification (if enabled)
    - Validates email format and DNS deliverability
    - Enforces strong password requirements (Pydantic validator)
    - Prevents account enumeration (uniform error messages)
    - Generates email verification token (Phase 7A)
    - Converts guest accounts (preserves teams)
    """
    # CAPTCHA verification (Phase 7A)
    await verify_captcha(user_data.captcha_token, get_real_client_ip(request))

    # Validate email format and DNS
    try:
        email_info = validate_email(user_data.email, check_deliverability=True)
        normalized_email = email_info.normalized.lower()
    except EmailNotValidError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email address",
        )

    # ANTI-ABUSE: Check if email is in deletion cooldown
    deleted = db.query(models.DeletedEmail).filter(
        models.DeletedEmail.email == normalized_email,
        models.DeletedEmail.cooldown_until > datetime.now(timezone.utc)
    ).first()

    if deleted:
        days_remaining = (deleted.cooldown_until - datetime.now(timezone.utc)).days + 1
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This email was recently used on a deleted account. "
                   f"You can register with it again in {days_remaining} days."
        )

    # SECURITY: Check if email exists (uniform error message)
    existing_user = db.query(models.User).filter(
        models.User.email == normalized_email
    ).first()

    if existing_user:
        # Don't reveal if email exists (account enumeration prevention)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Please try a different email address.",
        )

    # Trim and normalize username
    trimmed_username = trim_username(user_data.username)
    canonical = get_canonical_username(trimmed_username)

    # Check if username exists (exact match)
    existing_username = db.query(models.User).filter(
        models.User.username == trimmed_username
    ).first()

    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    # SECURITY: Check canonical username (blocks confusable look-alikes)
    # e.g., "аdmin" (Cyrillic а) is blocked if "admin" exists
    existing_canonical = db.query(models.User).filter(
        models.User.canonical_username == canonical
    ).first()

    if existing_canonical:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username too similar to an existing username",
        )

    # Hash password (bcrypt with auto-generated salt)
    hashed_pwd = hash_password(user_data.password)

    # Generate email verification token (Phase 7A)
    verification_token = generate_verification_token()
    verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

    # Case 1: Guest promotion (convert existing guest to registered)
    if current_user and current_user.is_guest:
        logger.info(f"Converting guest {current_user.username} to registered user {user_data.username}")

        # Re-query user from current session to ensure proper tracking
        user = db.query(models.User).filter(models.User.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.username = trimmed_username
        user.canonical_username = canonical
        user.email = normalized_email
        user.hashed_password = hashed_pwd
        user.is_guest = False
        user.subscription_tier = "free"  # Upgrade from "guest" to "free" tier
        user.email_verified = False  # Phase 7A: Require verification
        user.verification_token = verification_token
        user.verification_token_expires = verification_expires
        user.last_password_change = datetime.now(timezone.utc)
        user.preferred_language = user_data.preferred_language or "en"
        user.registration_ip = get_real_client_ip(request)
        user.converted_from_guest = True

        db.commit()
        db.refresh(user)

    # Case 2: New registration (no guest account)
    else:
        # Get device_id before creating the user so we can store it.
        # This allows find_device_owner() to identify the user after logout,
        # ensuring quota is inherited rather than resetting to anonymous.
        device_id_for_seed = getattr(request.state, 'device_id', None)
        if device_id_for_seed == "unknown-device":
            device_id_for_seed = None

        user = models.User(
            username=trimmed_username,
            canonical_username=canonical,
            email=normalized_email,
            hashed_password=hashed_pwd,
            is_guest=False,
            is_active=True,
            token_version=0,
            email_verified=False,  # Phase 7A: Require verification
            verification_token=verification_token,
            verification_token_expires=verification_expires,
            last_password_change=datetime.now(timezone.utc),
            preferred_language=user_data.preferred_language or "en",
            device_id=device_id_for_seed,
            registration_ip=get_real_client_ip(request),
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        # Transfer teams and quota from any prior guest account on this device.
        # Handles the case where a user saved teams as a guest, logged out, then
        # registered a fresh account — their data should follow them.
        prior_guest_id = None
        if device_id_for_seed and device_id_for_seed != "unknown-device":
            prior_guest = db.query(models.User).filter(
                models.User.device_id == device_id_for_seed,
                models.User.is_guest == True,
                models.User.is_active == True,
            ).first()
            if prior_guest:
                prior_guest_id = prior_guest.id
                try:
                    transferred = db.query(models.Team).filter(
                        models.Team.owner_id == prior_guest.id
                    ).update({"owner_id": user.id})
                    prior_guest.is_active = False
                    prior_guest.device_id = None
                    user.converted_from_guest = True
                    db.commit()
                    logger.info(
                        f"Transferred {transferred} team(s) from guest {prior_guest.id} "
                        f"to new user {user.id} ({user.username})"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to transfer teams from guest {prior_guest.id} "
                        f"to user {user.id}: {e}"
                    )
                    db.rollback()
                    prior_guest_id = None  # Skip quota transfer if teams transfer failed

        # Seed daily counter from device usage so quota display is honest.
        # Daily is read from the cross-account device cap (covers anon + guest usage).
        await seed_user_counter_from_device(user, device_id_for_seed)

        # Transfer monthly quota from the prior guest account (if any).
        # Monthly has no cross-account cap, so we sum guest + anon device monthly directly.
        if prior_guest_id is not None:
            await transfer_monthly_quota_from_guest(user, prior_guest_id, device_id_for_seed)

    # Send verification email
    email_sent = await send_verification_email(user.email, verification_token, language=user.preferred_language)
    logger.info(
        f"User registered: {user.username} (ID={user.id}), "
        f"email_sent={email_sent}"
    )

    # Generate tokens
    access_token = create_access_token(user.id, user.username, False, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)
    set_refresh_token_cookie(response, refresh_token)

    # Build response
    response_data = {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_to_user_out(user)
    }

    # DEV ONLY: Include verification token for testing (if SMTP not configured)
    if ENVIRONMENT == "development" and not email_sent:
        response_data["debug_verification_token"] = verification_token

    return response_data


@app.post("/auth/login", response_model=schemas.AuthResponse, tags=["Authentication"])
@limiter.limit("10/5minutes")  # SECURITY: Prevent brute force (account lock after 10 failed attempts provides additional protection)
async def login_user(
    request: Request,
    response: Response,
    credentials: schemas.UserLogin,
    db: Session = Depends(get_db)
):
    """
    Login with email and password.

    SECURITY:
    - Rate limited (10 attempts per 5 minutes per IP)
    - CAPTCHA verification (if enabled)
    - Account lockout after 10 failed attempts (30 min)
    - Uniform error messages (prevent account enumeration)
    - Updates last_login_at timestamp
    - Resets failed attempts counter on success
    """
    # CAPTCHA verification (Phase 7A)
    await verify_captcha(credentials.captcha_token, get_real_client_ip(request))

    # Fetch user by email
    user = db.query(models.User).filter(
        models.User.email == credentials.email.lower()
    ).first()

    # SECURITY: Check account lockout
    if user and user.locked_until:
        if user.locked_until > datetime.now(timezone.utc):
            minutes_left = max(1, (user.locked_until - datetime.now(timezone.utc)).seconds // 60)
            # Get language from request body for localized message
            language = getattr(credentials, "language", "en") or "en"
            if language == "zh":
                message = f"由于多次登录失败，账户已被锁定。请在 {minutes_left} 分钟后再试。"
            else:
                message = f"Account locked due to too many failed login attempts. Try again in {minutes_left} minutes."
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            )
        else:
            # Unlock account (lockout period expired)
            user.locked_until = None
            user.failed_login_attempts = 0
            db.commit()

    # SECURITY: Verify password (constant-time comparison via bcrypt)
    if not user or not user.hashed_password or not verify_password(credentials.password, user.hashed_password):
        # Failed login - increment counter
        account_just_locked = False
        if user:
            user.failed_login_attempts += 1

            # Lock account after 10 failed attempts
            if user.failed_login_attempts >= 10:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
                account_just_locked = True
                logger.warning(f"Account locked: {user.email} (ID={user.id})")

            db.commit()

        # SECURITY: Uniform error message (don't reveal if email exists)
        client_ip = get_real_client_ip(request)
        logger.warning(f"Failed login attempt for {credentials.email} from {client_ip}")

        # If account was just locked, show specific message (user already knows email exists after 10 attempts)
        if account_just_locked:
            language = getattr(credentials, "language", "en") or "en"
            if language == "zh":
                message = "由于多次登录失败，账户已被锁定。请在 30 分钟后再试。"
            else:
                message = "Account locked due to too many failed login attempts. Try again in 30 minutes."
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Successful login - reset failed attempts counter
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = get_real_client_ip(request)

    # Update device_id to the current device so find_device_owner() works after logout.
    # This also retroactively fixes existing users whose device_id was never stored.
    current_device_id = getattr(request.state, 'device_id', None)
    if current_device_id and current_device_id != "unknown-device":
        user.device_id = current_device_id

    # Auto-upgrade admin users to unlimited tier
    if is_admin_user(user) and user.subscription_tier != "unlimited":
        user.subscription_tier = "unlimited"
        logger.info(f"Auto-upgraded admin {user.email} to unlimited tier")

    db.commit()
    db.refresh(user)

    # Generate tokens
    access_token = create_access_token(user.id, user.username, user.is_guest, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)
    set_refresh_token_cookie(response, refresh_token)

    logger.info(f"User logged in: {user.username} (ID={user.id})")

    return schemas.AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_to_user_out(user)
    )


@app.post("/auth/refresh", response_model=schemas.TokenResponse, tags=["Authentication"])
async def refresh_access_token(
    request: Request,
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token"),
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token from httpOnly cookie.

    SECURITY:
    - Refresh token ONLY from cookie (never from request body)
    - Validates token type is 'refresh' (not 'access')
    - Checks token version (revocation)
    - Checks Redis blacklist (logout revocation)
    - Issues new access token (refresh token remains same)
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found. Please login again.",
        )

    try:
        payload = decode_token(refresh_token)

        # Verify token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        user_id = int(payload.get("sub"))
        token_version = payload.get("token_version", 0)
        jti = payload.get("jti")

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please login again.",
        )
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # SECURITY: Check if token has been revoked (logout blacklist)
    if await revocation_service.is_token_revoked(jti):
        logger.warning(f"Attempted use of revoked refresh token: {jti}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked. Please login again.",
        )

    # Fetch user
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # SECURITY: Check token version (revocation via version bump)
    if token_version != user.token_version:
        logger.warning(
            f"Token version mismatch for user {user.id}: "
            f"token={token_version}, user={user.token_version}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked. Please login again.",
        )

    # Issue new access token
    new_access_token = create_access_token(
        user.id,
        user.username,
        user.is_guest,
        user.token_version
    )

    logger.info(f"Refreshed access token for user {user.id}")

    return schemas.TokenResponse(
        access_token=new_access_token,
        token_type="bearer"
    )


@app.get("/auth/me", response_model=schemas.UserOut, tags=["Authentication"])
async def get_current_user_profile(
    current_user: models.User = Depends(get_current_user)
):
    """
    Get current user's profile.

    Requires valid access token in Authorization header.
    """
    return user_to_user_out(current_user)


@app.post("/auth/logout", tags=["Authentication"])
async def logout_user(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token"),
    current_user: models.User = Depends(get_current_user)
):
    """
    Logout current user (server-side token revocation).

    SECURITY:
    - Revokes refresh token by adding to Redis blacklist
    - Clears refresh token cookie
    - Frontend should clear access token from memory

    Note: Access tokens remain valid until expiry (15 minutes).
    For immediate revocation, use /auth/logout-all (bumps token_version).
    """
    # Revoke refresh token if present
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            jti = payload.get("jti")
            if jti:
                await revocation_service.revoke_token(jti, "refresh")
                logger.info(f"Revoked refresh token for user {current_user.id}")
        except:
            # Invalid token, ignore
            pass

    # Clear refresh token cookie
    clear_refresh_token_cookie(response)

    logger.info(f"User logged out: {current_user.username} (ID={current_user.id})")

    return {"message": "Logged out successfully"}


@app.post("/auth/logout-all", tags=["Authentication"])
async def logout_all_devices(
    response: Response,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Logout from all devices (invalidate ALL tokens immediately).

    SECURITY: Increments user.token_version to invalidate ALL tokens.

    Use this for:
    - Password change
    - Suspected account compromise
    - User requested "logout everywhere"
    """
    # Increment token version (invalidates all existing tokens)
    current_user.token_version += 1
    db.commit()

    # Clear refresh token cookie
    clear_refresh_token_cookie(response)

    logger.info(
        f"Logged out all devices for user {current_user.id} "
        f"(token_version={current_user.token_version})"
    )

    return {"message": "Logged out from all devices"}


@app.post("/auth/reset-device-id", tags=["Authentication"])
async def reset_device_id(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Clear guest data without changing the device ID cookie.

    Used for "Clear Guest Data" functionality:
    - Orphans the existing guest account (makes it inaccessible)
    - User can create a fresh guest account on the same device

    Intentionally keeps the same device_id so that:
    - Cross-account daily caps are preserved (prevents quota bypass via repeated clears)
    - The new guest account seeds its quota from existing device usage (shows correct count)

    This endpoint does NOT require authentication.
    """
    device_id = request.cookies.get(DEVICE_ID_COOKIE_NAME)
    if device_id:
        old_guest = db.query(models.User).filter(
            models.User.device_id == device_id,
            models.User.is_guest == True,
        ).first()
        if old_guest:
            old_guest.is_active = False
            old_guest.device_id = None
            db.commit()
            logger.info(f"Deactivated guest ID={old_guest.id} on clear-guest-data")

    return {"message": "Guest data cleared successfully"}


# ========== PASSWORD RESET (Phase 6) ==========

@app.post("/auth/forgot-password", tags=["Authentication"])
@limiter.limit("3/hour")  # Prevent email spam
async def forgot_password(
    request: Request,
    email_data: schemas.ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request password reset email.

    🔒 SECURITY:
    - CAPTCHA verification (if enabled)
    - Always returns success to prevent user enumeration
    - If email exists, generates reset token and logs it (email sending not implemented)
    """
    import secrets

    # CAPTCHA verification (Phase 7A)
    await verify_captcha(email_data.captcha_token, get_real_client_ip(request))

    # Find user by email
    user = db.query(models.User).filter(models.User.email == email_data.email.lower()).first()

    if user and not user.is_guest:
        # Generate reset token (valid for 1 hour)
        reset_token = secrets.token_urlsafe(32)
        user.password_reset_token = reset_token
        user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()

        # Send password reset email
        email_sent = await send_password_reset_email(user.email, reset_token, language=user.preferred_language)
        logger.info(
            f"Password reset requested for {user.email}, email_sent={email_sent}"
        )

    # ✅ ALWAYS return success (prevent user enumeration)
    return {
        "message": "If an account exists with that email, a password reset link has been sent."
    }


@app.post("/auth/reset-password", tags=["Authentication"])
@limiter.limit("5/hour")
async def reset_password(
    request: Request,
    reset_data: schemas.PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Reset password using token from email.

    🔒 SECURITY:
    - Token is single-use (cleared after successful reset)
    - Token expires after 1 hour
    - Increments token_version (invalidates all existing sessions)
    """
    # Find user by reset token
    user = db.query(models.User).filter(
        models.User.password_reset_token == reset_data.token
    ).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Check token expiry
    if not user.password_reset_expires or datetime.now(timezone.utc) > user.password_reset_expires:
        raise HTTPException(status_code=400, detail="Reset token has expired")

    # Reset password
    user.hashed_password = hash_password(reset_data.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    user.last_password_change = datetime.now(timezone.utc)

    # ✅ SECURITY: Increment token_version to invalidate all existing sessions
    user.token_version += 1

    db.commit()

    logger.info(f"Password reset successful for user {user.id}")

    return {"message": "Password reset successful. Please log in with your new password."}


@app.post("/auth/change-password", tags=["Authentication"])
async def change_password(
    password_data: schemas.PasswordChangeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change password (requires current password).

    Different from reset: user must be logged in and know current password.
    """
    if current_user.is_guest:
        raise HTTPException(
            status_code=403,
            detail="Guest users cannot change password. Register an account first."
        )

    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Re-query user to ensure proper session tracking for updates
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update password
    user.hashed_password = hash_password(password_data.new_password)
    user.last_password_change = datetime.now(timezone.utc)

    # ✅ SECURITY: Increment token_version to invalidate all existing sessions
    user.token_version += 1

    db.commit()

    logger.info(f"Password changed for user {user.id}")

    return {"message": "Password changed successfully. Please log in again."}


# ========== EMAIL CHANGE (Phase 6) ==========

@app.post("/auth/change-email", tags=["Authentication"])
@limiter.limit("5/hour")
async def request_email_change(
    request: Request,
    email_data: schemas.EmailChangeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Request email change (requires password verification).

    Flow:
    1. User submits new email + current password
    2. Server verifies password
    3. Server generates token and stores in pending_email fields
    4. In production: Send verification email to NEW address
    5. User clicks link to confirm

    SECURITY:
    - Requires password verification to prevent unauthorized changes
    - Token sent to NEW email (prevents hijacking)
    - Existing email remains until new one is verified
    """
    if current_user.is_guest:
        raise HTTPException(
            status_code=403,
            detail="Guest users cannot change email. Register an account first."
        )

    # Re-query user for session tracking
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify password
    if not verify_password(email_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect")

    # Check if new email is same as current
    if user.email and user.email.lower() == email_data.new_email.lower():
        raise HTTPException(status_code=400, detail="New email is the same as current email")

    # Check if new email is already taken
    existing = db.query(models.User).filter(
        models.User.email == email_data.new_email.lower(),
        models.User.id != user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email address is already in use")

    # Generate verification token
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)  # 24 hour expiry

    # Store pending email change
    user.pending_email = email_data.new_email.lower()
    user.email_change_token = token
    user.email_change_token_expires = expires

    db.commit()

    # Send verification email to new address
    email_sent = await send_email_change_verification(user.pending_email, token, language=user.preferred_language)
    logger.info(
        f"Email change requested for user {user.id}: {user.email} -> {user.pending_email}, "
        f"email_sent={email_sent}"
    )

    # Build response
    response_data = {
        "message": "Verification email sent to new address. Please check your inbox."
    }

    # DEV ONLY: Include token for testing (if SMTP not configured)
    if ENVIRONMENT == "development" and not email_sent:
        response_data["debug_token"] = token

    return response_data


@app.post("/auth/confirm-email-change", tags=["Authentication"])
@limiter.limit("5/hour")
async def confirm_email_change(
    request: Request,
    confirm_data: schemas.EmailChangeConfirmRequest,
    db: Session = Depends(get_db)
):
    """
    Confirm email change with token from verification email.

    SECURITY:
    - Token must be valid and not expired
    - Old email is replaced with new email
    - email_verified is set to True (link click proves ownership of new email)
    - All sessions are invalidated
    """
    # Find user with this token
    user = db.query(models.User).filter(
        models.User.email_change_token == confirm_data.token
    ).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Check expiry (handle None case - treat missing expiry as expired)
    if not user.email_change_token_expires or user.email_change_token_expires < datetime.now(timezone.utc):
        # Clear expired token
        user.email_change_token = None
        user.email_change_token_expires = None
        user.pending_email = None
        db.commit()
        raise HTTPException(status_code=400, detail="Token has expired. Please request a new email change.")

    # Check for pending email
    if not user.pending_email:
        raise HTTPException(status_code=400, detail="No pending email change found")

    # Final check: ensure pending email isn't taken (race condition protection)
    existing = db.query(models.User).filter(
        models.User.email == user.pending_email,
        models.User.id != user.id
    ).first()
    if existing:
        user.email_change_token = None
        user.email_change_token_expires = None
        user.pending_email = None
        db.commit()
        raise HTTPException(status_code=400, detail="Email address is already in use")

    old_email = user.email
    new_email = user.pending_email

    # Update email
    user.email = new_email
    user.pending_email = None
    user.email_change_token = None
    user.email_change_token_expires = None

    # Clicking the confirmation link proves ownership of the new email
    user.email_verified = True

    # Invalidate all sessions for security
    user.token_version += 1

    db.commit()

    logger.info(f"Email changed for user {user.id}: {old_email} -> {new_email}")

    return {"message": "Email changed successfully. Please log in with your new email."}


# ========== ACCOUNT DELETION (Phase 6) ==========

@app.delete("/auth/account", tags=["Authentication"])
async def delete_account(
    response: Response,
    delete_data: schemas.AccountDeleteRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Permanently delete user account and all associated data.

    SECURITY:
    - Requires password verification
    - Requires typing confirmation phrase
    - Cannot delete system user
    - Deletes all teams and associated data (cascade)
    - Clears auth cookies

    WARNING: This action is IRREVERSIBLE.
    """
    if current_user.is_guest:
        raise HTTPException(
            status_code=403,
            detail="Guest accounts are automatically cleaned up. Register to create a permanent account."
        )

    if current_user.is_system:
        raise HTTPException(
            status_code=403,
            detail="System accounts cannot be deleted"
        )

    # Re-query user for proper session tracking
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify password
    if not verify_password(delete_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect")

    # Log deletion (before deleting)
    logger.warning(
        f"ACCOUNT DELETION: User {user.id} ({user.username}, {user.email}) "
        f"requested account deletion"
    )

    # Store info for response
    username = user.username
    user_email = user.email
    team_count = len(user.teams) if user.teams else 0

    # Record email in deleted_emails table BEFORE deletion (anti-abuse)
    # Prevents immediate re-registration with the same email
    EMAIL_COOLDOWN_DAYS = 30
    if user_email:
        deleted_email = models.DeletedEmail(
            email=user_email.lower(),
            cooldown_until=datetime.now(timezone.utc) + timedelta(days=EMAIL_COOLDOWN_DAYS),
            original_user_id=user.id,
            reason="user_requested"
        )
        db.add(deleted_email)

    # Delete user (cascades to teams, user_monsters, talents, analyses)
    db.delete(user)
    db.commit()

    # Clear auth cookies
    response.delete_cookie(
        key="refresh_token",
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE
    )

    logger.info(f"Account deleted: {username} (ID: {current_user.id}, Teams: {team_count})")

    return {
        "message": f"Account '{username}' has been permanently deleted.",
        "deleted_teams": team_count
    }


# ========== EMAIL VERIFICATION (Phase 7A) ==========

@app.post("/auth/verify-email", tags=["Authentication"])
@limiter.limit("10/hour")
async def verify_email(
    request: Request,
    verify_data: schemas.EmailVerifyRequest,
    db: Session = Depends(get_db)
):
    """
    Verify email address with token from verification email.

    SECURITY:
    - Token must be valid and not expired
    - Sets email_verified to True
    - Clears verification token after use
    """
    # Find user with this token
    user = db.query(models.User).filter(
        models.User.verification_token == verify_data.token
    ).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    # Check expiry
    if user.verification_token_expires and user.verification_token_expires < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="Verification token has expired. Please request a new one."
        )

    # Already verified?
    if user.email_verified:
        return {"message": "Email is already verified"}

    # Verify email
    user.email_verified = True
    user.verification_token = None
    user.verification_token_expires = None

    db.commit()

    logger.info(f"Email verified for user {user.id} ({user.email})")

    return {"message": "Email verified successfully. You now have full access to all features."}


@app.post("/auth/resend-verification", tags=["Authentication"])
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Resend verification email to current user.

    SECURITY:
    - Requires authentication
    - Rate limited to prevent spam
    - Generates new token (invalidates old one)
    """
    if current_user.is_guest:
        raise HTTPException(
            status_code=403,
            detail="Guest accounts don't have email to verify. Please register first."
        )

    if current_user.email_verified:
        return {"message": "Email is already verified"}

    # Re-query for session tracking
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate new verification token
    verification_token = generate_verification_token()
    verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

    user.verification_token = verification_token
    user.verification_token_expires = verification_expires

    db.commit()

    # Send verification email
    email_sent = await send_verification_email(user.email, verification_token, language=user.preferred_language)
    logger.info(f"Verification email resent for user {user.id} ({user.email}), email_sent={email_sent}")

    # Build response
    response_data = {
        "message": "Verification email sent. Please check your inbox."
    }

    # DEV ONLY: Include token for testing (if SMTP not configured)
    if ENVIRONMENT == "development" and not email_sent:
        response_data["debug_token"] = verification_token

    return response_data


@app.patch("/auth/update-language-preference", tags=["Authentication"])
@limiter.limit("10/hour")
async def update_language_preference(
    request: Request,
    data: schemas.UpdateLanguageRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the authenticated user's preferred language for transactional emails.

    No password required. Rejected for guest users (guests have no persistent profile).
    """
    if current_user.is_guest:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest users cannot set a language preference"
        )

    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.preferred_language = data.preferred_language
    db.commit()

    logger.info(f"Language preference updated for user {user.id}: {data.preferred_language}")
    return {"preferred_language": user.preferred_language}


# ========== HEALTH CHECK ==========

@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


@app.get("/config/captcha", tags=["System"])
def get_captcha_settings():
    """Get CAPTCHA configuration for frontend."""
    return get_captcha_config()


@app.get("/auth/usage", tags=["Authentication"])
async def get_user_usage(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's usage statistics and tier limits.

    Returns:
    - Current subscription tier
    - Daily/monthly analysis usage and limits
    - Team count and limit
    """
    stats = await get_usage_stats(current_user)

    # Add team count
    team_count = db.query(models.Team).filter(
        models.Team.owner_id == current_user.id
    ).count()
    stats["teams_used"] = team_count

    return stats


@app.get("/auth/quota", tags=["Authentication"])
async def get_quota(
    request: Request,
    user_or_anon: tuple = Depends(get_user_or_anonymous),
    db: Session = Depends(get_db)
):
    """
    Get quota/usage statistics for any user (anonymous, guest, or registered).

    Works for ALL tiers:
    - Anonymous: Tracked by device_id + IP (returns anonymous tier limits)
    - Guest: Tracked by user.id (returns guest tier limits)
    - Registered: Tracked by user.id (returns free/premium tier limits)

    Returns:
    - tier: Current tier name
    - daily_used/daily_limit: Daily analysis quota
    - monthly_used/monthly_limit: Monthly analysis quota
    - teams_used/teams_limit: Team count quota
    - is_anonymous: True if user is not authenticated
    """
    user, device_id, client_ip = user_or_anon

    if user is None:
        # Anonymous user - check if device belongs to an existing account
        # This prevents "double-dipping" by logging out for fresh anonymous quota
        device_owner = find_device_owner(device_id, db)
        if device_owner:
            # Device has an account - show that account's quota
            # (prevents double-dipping by logging out for fresh anonymous quota)
            #
            # SECURITY: Redact fields that would leak account details to
            # an unauthenticated caller.  The frontend already hides the
            # teams section when is_anonymous=True, but we must not send
            # the real count over the wire either.  is_guest is also
            # unnecessary for the anonymous quota display.
            stats = await get_usage_stats(device_owner)
            stats["teams_used"] = 0          # redacted — login to see real count
            stats["teams_limit"] = 0         # redacted — consistent with teams_used
            stats["is_anonymous"] = True
            # NOTE: is_guest intentionally omitted to avoid revealing account type
            return stats
        else:
            # Truly anonymous - no account on this device
            stats = await get_anonymous_usage_stats(device_id, client_ip)
            stats["is_anonymous"] = True
            stats["teams_used"] = 0
            return stats
    else:
        # Authenticated user (guest or registered)
        stats = await get_usage_stats(user)

        # Add team count
        team_count = db.query(models.Team).filter(
            models.Team.owner_id == user.id
        ).count()
        stats["teams_used"] = team_count
        stats["is_anonymous"] = False
        stats["is_guest"] = user.is_guest

        return stats


# === GET Endpoints ===

@app.get("/")
def read_root():
    return {"message": "Welcome to Roco Team Builder!"}

@app.get("/cache/stats")
def get_cache_stats():
    """Get cache statistics for monitoring."""
    return {
        "llm_cache_size": len(llm_cache._cache),
        "ttl_seconds": llm_cache.ttl_seconds
    }

@app.post("/cache/clear")
async def clear_cache():
    """
    Clear all LLM cache entries and reference resolver cache (admin endpoint).

    🔒 SECURITY: Disabled in production until auth is implemented.
    Anyone can DOS the app by clearing cache repeatedly, causing:
    - Increased LLM costs (cache misses)
    - Slower response times
    - Service degradation

    TODO: After implementing auth (see auth-implementation-complete.md),
    change to: async def clear_cache(current_user: User = Depends(require_admin))
    """
    # ⚠️ SECURITY: Disable in production until auth is implemented
    if ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is disabled in production. Enable authentication first."
        )

    # Clear in-memory cache
    llm_cache.clear()

    # Clear Redis cache (namespace-based, safe for auth tokens)
    if redis_cache and redis_cache._connected:
        await redis_cache.clear()

    # Clear reference resolver cache
    reference_resolver.invalidate_reference_cache()

    return {
        "message": "Cache cleared successfully",
        "in_memory_cache_size": len(llm_cache._cache),
        "redis_cache": "cleared" if redis_cache and redis_cache._connected else "not available"
    }

@app.get("/monsters", response_model=List[schemas.MonsterLiteOut])
def get_monsters(
    db: Session = Depends(get_db),
    name: Optional[str] = Query(None),
    type_id: Optional[int] = Query(None),
    trait_id: Optional[int] = Query(None),
    is_leader_form: Optional[bool] = Query(None),
    species_id: Optional[int] = Query(None),
    evolves_from_id: Optional[int] = Query(None),
    limit: int = Query(1000, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    query = db.query(models.Monster).options(
        joinedload(models.Monster.main_type),
        joinedload(models.Monster.sub_type),
        joinedload(models.Monster.default_legacy_type),
    )

    if name:
        term = f"%{name}%"

        # Dialect-aware JSON -> text extraction for localized.zh.name / localized.zh.form
        dialect = db.bind.dialect.name

        if dialect == "postgresql":
            zh_name_expr = cast(models.Monster.localized['zh']['name'].astext, String)
            zh_form_expr = cast(models.Monster.localized['zh']['form'].astext, String)
        elif dialect == "sqlite":
            zh_name_expr = func.json_extract(models.Monster.localized, '$.zh.name')
            zh_form_expr = func.json_extract(models.Monster.localized, '$.zh.form')
        else:
            zh_name_expr = None
            zh_form_expr = None

        # Allow searching both English name and form column
        filters = [models.Monster.name.ilike(term)]
        filters.append(models.Monster.form.ilike(term))

        if zh_name_expr is not None:
            filters.append(cast(zh_name_expr, String).ilike(term))
        if zh_form_expr is not None:
            filters.append(cast(zh_form_expr, String).ilike(term))

        query = query.filter(or_(*filters))

    if type_id:
        query = query.filter(or_(
            models.Monster.main_type_id == type_id,
            models.Monster.sub_type_id == type_id,
            models.Monster.default_legacy_type_id == type_id,
        ))

    if trait_id:
        query = query.filter(models.Monster.trait_id == trait_id)

    if is_leader_form is not None:
        query = query.filter(models.Monster.is_leader_form == is_leader_form)

    if species_id is not None:
        query = query.filter(models.Monster.species_id == species_id)

    if evolves_from_id is not None:
        query = query.filter(models.Monster.evolves_from_id == evolves_from_id)

    # Sort by canonical wiki dex_number when available; fall back to id so
    # monsters without a wiki match keep their existing relative position.
    # id is also used as a tie-breaker between equal effective dex positions.
    query = query.order_by(
        func.coalesce(models.Monster.dex_number, models.Monster.id).asc(),
        models.Monster.id.asc(),
    )

    return query.offset(offset).limit(limit).all()

def build_evolution_tree(monster_id: int, db: Session) -> dict | None:
    """
    Build complete evolution tree for a monster's species.
    Returns tree structure organized by evolution stages.
    Leader forms are collapsed to single representative per monster name.
    """
    from sqlalchemy import text
    from collections import defaultdict

    # 1. Get the monster to determine species_id
    monster = db.query(models.Monster).filter(
        models.Monster.id == monster_id
    ).first()

    if not monster:
        return None

    # 2. Use recursive CTE to get ALL monsters in this species with depth
    recursive_query = text("""
        WITH RECURSIVE evolution_tree AS (
            -- Base case: Find root (monster with no parent in same species)
            SELECT id, name, form, species_id, evolves_from_id,
                   is_leader_form, leader_potential,
                   main_type_id, sub_type_id, 0 as depth
            FROM monsters
            WHERE species_id = :species_id
              AND evolves_from_id IS NULL

            UNION ALL

            -- Recursive: Find children
            SELECT m.id, m.name, m.form, m.species_id, m.evolves_from_id,
                   m.is_leader_form, m.leader_potential,
                   m.main_type_id, m.sub_type_id, et.depth + 1
            FROM monsters m
            JOIN evolution_tree et ON m.evolves_from_id = et.id
            WHERE m.species_id = :species_id
        )
        SELECT DISTINCT * FROM evolution_tree
        ORDER BY depth, name, form
    """)

    # 3. Execute and fetch all nodes
    result = db.execute(recursive_query, {"species_id": monster.species_id})
    nodes_data = result.fetchall()

    if not nodes_data:
        return None

    # 4. Load full monster objects with relationships
    node_ids = [row.id for row in nodes_data]
    monsters = db.query(models.Monster).options(
        joinedload(models.Monster.main_type),
        joinedload(models.Monster.sub_type),
    ).filter(models.Monster.id.in_(node_ids)).all()

    depth_map = {row.id: row.depth for row in nodes_data}

    # 5. Build tree structure organized by stages
    stages_dict = defaultdict(list)
    evolves_from_map = {m.id: m.evolves_from_id for m in monsters}

    for m in monsters:
        depth = depth_map[m.id]
        monster_data = {
            "id": m.id,
            "name": m.name,
            "form": m.form,
            "localized": m.localized,
            "is_leader_form": m.is_leader_form,
            "main_type": schemas.TypeOut.model_validate(m.main_type).model_dump() if m.main_type else None,
            "sub_type": schemas.TypeOut.model_validate(m.sub_type).model_dump() if m.sub_type else None,
            "evolution_level": m.evolution_level,
            "evolution_condition": m.evolution_condition,
        }
        stages_dict[depth].append(monster_data)

    # 6. Collapse leader forms - group by name (ignoring form)
    stages_list = []
    for depth in sorted(stages_dict.keys()):
        monsters_at_depth = stages_dict[depth]

        # Check if this is a leader stage
        is_leader_stage = all(m["is_leader_form"] for m in monsters_at_depth)

        if is_leader_stage:
            # Group leader forms by monster name
            leader_groups = defaultdict(list)
            for m in monsters_at_depth:
                leader_groups[m["name"]].append(m)

            # Keep only lowest ID per name as representative
            collapsed_monsters = []
            for name, forms in leader_groups.items():
                # Sort by ID, pick lowest
                forms_sorted = sorted(forms, key=lambda x: x["id"])
                representative = forms_sorted[0]

                # Mark as representative if multiple forms exist
                if len(forms) > 1:
                    representative["is_representative"] = True
                    representative["representative_id"] = representative["id"]

                collapsed_monsters.append(representative)

            stages_list.append({
                "depth": depth,
                "is_leader_stage": True,
                "monsters": collapsed_monsters
            })
        else:
            stages_list.append({
                "depth": depth,
                "monsters": monsters_at_depth
            })

    # 7. Sort monsters within each stage for consistent visual alignment.
    #    Stage 0: sort by ID (deterministic insertion order).
    #    Later stages: sort by parent's position in the previous stage so
    #    same-form rows stay visually aligned across all evo columns, with
    #    ID as tiebreaker for siblings that share the same parent.
    if stages_list:
        stages_list[0]["monsters"].sort(key=lambda m: m["id"])
    for i in range(1, len(stages_list)):
        prev_id_to_pos = {m["id"]: idx for idx, m in enumerate(stages_list[i - 1]["monsters"])}

        def _sort_key(m, _prev=prev_id_to_pos, _ef=evolves_from_map):
            parent_pos = _prev.get(_ef.get(m["id"]), 999)
            return (parent_pos, m["id"])

        stages_list[i]["monsters"].sort(key=_sort_key)

    # 8. Calculate metadata
    max_depth = max(depth_map.values()) if depth_map else 0
    total_unique_monsters = sum(len(stage["monsters"]) for stage in stages_list)

    return {
        "stages": stages_list,
        "max_depth": max_depth,
        "total_unique_monsters": total_unique_monsters,
        "species_id": monster.species_id,
        "current_monster_id": monster_id
    }


@app.get("/monsters/{monster_id}", response_model=schemas.MonsterOut)
def get_monster_detail(monster_id: int, db: Session = Depends(get_db)):
    monster = db.query(models.Monster).options(
        joinedload(models.Monster.main_type),
        joinedload(models.Monster.sub_type),
        joinedload(models.Monster.default_legacy_type),
        joinedload(models.Monster.trait),
        joinedload(models.Monster.species),
        joinedload(models.Monster.move_pool).joinedload(models.Move.move_type),
        joinedload(models.Monster.move_stones).joinedload(models.Move.move_type),
        joinedload(models.Monster.legacy_moves)
    ).filter(models.Monster.id == monster_id).first()
    if not monster:
        raise HTTPException(status_code=404, detail="Jingling not found")

    # Build evolution tree
    evolution_tree = build_evolution_tree(monster_id, db)

    # Convert to Pydantic model and add evolution_tree
    result = schemas.MonsterOut.model_validate(monster)
    result.evolution_tree = evolution_tree

    return result


@app.get("/moves", response_model=List[schemas.MoveOut])
def get_moves(
    db: Session = Depends(get_db),
    ids: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    move_type_id: Optional[int] = Query(None),
    move_category: Optional[schemas.MoveCategory] = Query(None),
    has_counter: Optional[bool] = Query(None),
    limit: int = Query(500, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = db.query(models.Move).options(
        joinedload(models.Move.move_type)
    )
    # allow fetching by a specific set of ids (comma-separated)
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.filter(models.Move.id.in_(id_list))
            return query.order_by(models.Move.id).all()
    if name:
        query = query.filter(models.Move.name.ilike(f"%{name}%"))
    if move_type_id:
        query = query.filter(models.Move.move_type_id == move_type_id)
    if move_category:
        query = query.filter(models.Move.move_category == models.MoveCategory(move_category.value))
    if has_counter is not None:
        query = query.filter(models.Move.has_counter == has_counter)
    return query.order_by(models.Move.id).offset(offset).limit(limit).all()

@app.get("/moves/{move_id}", response_model=schemas.MoveOut)
def get_move_detail(move_id: int, db: Session = Depends(get_db)):
    move = db.query(models.Move).options(
        joinedload(models.Move.move_type)
    ).filter(models.Move.id == move_id).first()
    if not move:
        raise HTTPException(status_code=404, detail="Move not found")
    return move


@app.get("/moves/{move_id}/learners", response_model=schemas.MoveLearnersOut)
def get_move_learners(move_id: int, db: Session = Depends(get_db)):
    move = db.get(models.Move, move_id)
    if not move:
        raise HTTPException(status_code=404, detail="Move not found")

    base_opts = [
        joinedload(models.Monster.main_type),
        joinedload(models.Monster.sub_type),
        joinedload(models.Monster.default_legacy_type),
    ]

    # Only return highest-form non-leader monsters.
    # A monster is "highest form" if no other non-leader monster evolves from it.
    parent_ids_subq = (
        db.query(models.Monster.evolves_from_id)
        .filter(
            models.Monster.evolves_from_id.isnot(None),
            models.Monster.is_leader_form == False,
        )
        .scalar_subquery()
    )
    highest_form_filters = [
        models.Monster.is_leader_form == False,
        ~models.Monster.id.in_(parent_ids_subq),
    ]

    # Use the same dex-order sort as the /monsters endpoint so the move
    # learners list matches the dex grid's visual sequence.
    dex_order = (
        func.coalesce(models.Monster.dex_number, models.Monster.id).asc(),
        models.Monster.id.asc(),
    )

    pool = (
        db.query(models.Monster)
        .join(models.monster_moves, models.Monster.id == models.monster_moves.c.monster_id)
        .filter(
            models.monster_moves.c.move_id == move_id,
            models.monster_moves.c.is_move_stone == False,
            *highest_form_filters,
        )
        .options(*base_opts)
        .order_by(*dex_order)
        .all()
    )

    stones = (
        db.query(models.Monster)
        .join(models.monster_moves, models.Monster.id == models.monster_moves.c.monster_id)
        .filter(
            models.monster_moves.c.move_id == move_id,
            models.monster_moves.c.is_move_stone == True,
            *highest_form_filters,
        )
        .options(*base_opts)
        .order_by(*dex_order)
        .all()
    )

    legacy_ids = [
        row[0] for row in
        db.query(models.LegacyMove.monster_id)
        .filter(models.LegacyMove.move_id == move_id)
        .all()
    ]
    legacy = (
        db.query(models.Monster)
        .filter(
            models.Monster.id.in_(legacy_ids),
            *highest_form_filters,
        )
        .options(*base_opts)
        .order_by(*dex_order)
        .all()
    ) if legacy_ids else []

    return {"move_pool": pool, "move_stones": stones, "legacy": legacy}


@app.get("/traits", response_model=List[schemas.TraitOut])
def get_traits(db: Session = Depends(get_db)):
    return db.query(models.Trait).order_by(models.Trait.id).all()


@app.get("/types", response_model=List[schemas.TypeWithMatchupsOut])
def get_types(db: Session = Depends(get_db)):
    return (
        db.query(models.Type)
        .options(
            joinedload(models.Type.vulnerable_to),
            joinedload(models.Type.resistant_to),
        )
        .order_by(models.Type.id)
        .all()
    )


@app.get("/personalities", response_model=List[schemas.PersonalityOut])
def get_personalities(db: Session = Depends(get_db)):
    return db.query(models.Personality).order_by(models.Personality.id).all()


@app.get("/magic_items", response_model=List[schemas.MagicItemOut])
def get_magic_items(db: Session = Depends(get_db)):
    return db.query(models.MagicItem).order_by(models.MagicItem.id).all()


@app.get("/game_terms", response_model=List[schemas.GameTermOut])
def get_game_terms(db: Session = Depends(get_db)):
    return db.query(models.GameTerm).order_by(models.GameTerm.sort_order, models.GameTerm.id).all()


@app.get("/species", response_model=List[schemas.MonsterSpeciesOut])
def get_species(db: Session = Depends(get_db)):
    return db.query(models.MonsterSpecies).order_by(models.MonsterSpecies.id).all()


@app.get("/teams", response_model=List[schemas.TeamOut], tags=["Teams"])
def list_teams(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List teams owned by current user.

    SECURITY: Users can only see their own teams.
    """
    return (
        db.query(models.Team)
        .filter(models.Team.owner_id == current_user.id)  # Filter by owner
        .options(
            joinedload(models.Team.owner),  # Include owner info
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.main_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.sub_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.default_legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.personality),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move1),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move2),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move3),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move4),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.talent),
            joinedload(models.Team.magic_item),
        )
        .order_by(models.Team.id.desc())
        .all()
    )

@app.get("/teams/featured", response_model=List[schemas.TeamOut], tags=["Teams"])
@limiter.limit("30/minute")
async def get_featured_teams(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get all admin-curated featured teams.

    PUBLIC: No authentication required. Used by the Quick Build feature.
    Results are cached in Redis for 5 minutes.
    """
    cache_key = "featured_teams:list"

    # Try cache first
    cached = await redis_cache.get(cache_key)
    if cached is not None:
        return cached

    teams = (
        db.query(models.Team)
        .filter(models.Team.is_featured == True)
        .options(
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.main_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.sub_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.default_legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.personality),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move1),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move2),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move3),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move4),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.talent),
            joinedload(models.Team.magic_item),
        )
        .order_by(models.Team.id)
        .all()
    )

    # Serialize to dicts for caching (Pydantic v2 compatible).
    # SECURITY: redact the owner — this endpoint is public and TeamOut.owner
    # would otherwise lazy-load and expose the system user's profile (email,
    # tier, timestamps) to unauthenticated callers.
    serialized = []
    for t in teams:
        data = schemas.TeamOut.model_validate(t).model_dump(mode="json")
        data["owner"] = None
        data["owner_id"] = None
        serialized.append(data)
    await redis_cache.set(cache_key, serialized, ttl=300)

    return serialized


@app.get("/teams/{team_id}", response_model=schemas.TeamOut, tags=["Teams"])
def get_team(
    team_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a team by ID.

    SECURITY: Only owner can view.
    """
    db_team = (
        db.query(models.Team)
        .options(
            joinedload(models.Team.owner),  # Include owner info
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.main_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.sub_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.monster)
                .joinedload(models.Monster.default_legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.personality),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.legacy_type),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move1),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move2),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move3),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.move4),
            joinedload(models.Team.user_monsters)
                .joinedload(models.UserMonster.talent),
            joinedload(models.Team.magic_item),
        )
        .filter(models.Team.id == team_id)
        .first()
    )
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")

    # SECURITY: Check ownership
    if db_team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this team"
        )

    return db_team


# -------- POST Endpoints --------

@app.post("/teams", response_model=schemas.TeamOut, tags=["Teams"])
async def create_team(
    team: schemas.TeamCreate,
    lang: str = Query("en", description="Language for error messages (en/zh)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new team.

    SECURITY: Team automatically assigned to current user.
    Tier-based limits apply (Phase 7A).
    """
    # Check tier-based team limit (Phase 7A)
    await check_teams_limit(current_user, db, lang)

    # Check for duplicate team name for this user (case-sensitive)
    existing = db.query(models.Team).filter(
        models.Team.name == team.name,
        models.Team.owner_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"You already have a team with the name '{team.name}'"
        )

    # Persist the team and its monsters to DB
    db_team = models.Team(
        name=team.name,
        magic_item_id=team.magic_item_id,
        owner_id=current_user.id  # Set owner
    )
    db.add(db_team)
    db.flush()

    user_monsters_out = []   # For future expand reference
    for um in team.user_monsters:
        db_um = models.UserMonster(
            monster_id=um.monster_id,
            personality_id=um.personality_id,
            legacy_type_id=um.legacy_type_id,
            move1_id=um.move1_id,
            move2_id=um.move2_id,
            move3_id=um.move3_id,
            move4_id=um.move4_id,
            team_id=db_team.id,
            position=um.position
        )
        db.add(db_um)
        db.flush()
        db_talent = models.Talent(
            monster_instance_id=db_um.id,
            hp_boost=um.talent.hp_boost,
            phy_atk_boost=um.talent.phy_atk_boost,
            mag_atk_boost=um.talent.mag_atk_boost,
            phy_def_boost=um.talent.phy_def_boost,
            mag_def_boost=um.talent.mag_def_boost,
            spd_boost=um.talent.spd_boost
        )
        db.add(db_talent)
        db_um.talent = db_talent
        user_monsters_out.append(db_um)  # For future expand reference
    try:
        db.commit()
    except IntegrityError:
        # Bad foreign keys (nonexistent monster/move/personality/type/magic item)
        # are a client error, not a server crash
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Team references a jingling, move, personality, legacy type, or magic item that does not exist"
        )

    # Re-fetch with relationships for output schema
    db.refresh(db_team)

    logger.info(f"Created team {db_team.id} for user {current_user.id}")

    return db_team


# -------- PUT Team (Update) --------

@app.put("/teams/{team_id}", response_model=schemas.TeamOut, tags=["Teams"])
def update_team(
    team_id: int,
    team_update: schemas.TeamUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a team.

    SECURITY: Only owner can modify.
    """
    db_team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")

    # SECURITY: Check ownership
    if db_team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this team"
        )

    # Check for duplicate team name for this user (case-sensitive), excluding current team
    if team_update.name is not None:
        existing = db.query(models.Team).filter(
            models.Team.name == team_update.name,
            models.Team.id != team_id,
            models.Team.owner_id == current_user.id  # Check within user's teams only
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"You already have another team with the name '{team_update.name}'"
            )

    # Snapshot the analysis-relevant composition BEFORE mutating, so we can
    # invalidate stale saved analyses when the composition actually changes
    # (a name-only edit keeps them). Computed from plain values, not ORM
    # collections, to avoid flush-state ambiguity.
    def _talent_tuple(t):
        if t is None:
            return ()  # empty tuple keeps the sort comparable
        return (t.hp_boost, t.phy_atk_boost, t.mag_atk_boost,
                t.phy_def_boost, t.mag_def_boost, t.spd_boost)

    old_composition = (
        db_team.magic_item_id,
        tuple(sorted(
            (um.monster_id, um.personality_id, um.legacy_type_id,
             um.move1_id, um.move2_id, um.move3_id, um.move4_id,
             _talent_tuple(um.talent))
            for um in db_team.user_monsters
        )),
    )
    new_composition = (
        team_update.magic_item_id if team_update.magic_item_id is not None else db_team.magic_item_id,
        tuple(sorted(
            (um.monster_id, um.personality_id, um.legacy_type_id,
             um.move1_id, um.move2_id, um.move3_id, um.move4_id,
             _talent_tuple(um.talent))
            for um in team_update.user_monsters
        )),
    )

    # Update team fields if provided
    if team_update.name is not None:
        db_team.name = team_update.name
    if team_update.magic_item_id is not None:
        db_team.magic_item_id = team_update.magic_item_id

    # --- UserMonsters sync logic ---
    # Build a mapping of incoming user_monsters by id (if present)
    incoming_by_id = {um.id: um for um in team_update.user_monsters if um.id is not None}

    # Build a set of incoming user_monster ids (for those to keep/update)
    incoming_ids = set(incoming_by_id.keys())

    # Remove any user_monsters not in the new request
    for db_um in list(db_team.user_monsters):
        if db_um.id not in incoming_ids:
            db.delete(db_um)

    db.flush()

    # Update existing and add new user_monsters
    existing_ums = {um.id: um for um in db_team.user_monsters}

    for um_data in team_update.user_monsters:
        if um_data.id is not None and um_data.id in existing_ums:
            # Update existing user_monster
            um = existing_ums[um_data.id]
            um.monster_id = um_data.monster_id
            um.personality_id = um_data.personality_id
            um.legacy_type_id = um_data.legacy_type_id
            um.move1_id = um_data.move1_id
            um.move2_id = um_data.move2_id
            um.move3_id = um_data.move3_id
            um.move4_id = um_data.move4_id
            um.position = um_data.position
            # Update nested talent
            if um.talent:
                t = um_data.talent
                um.talent.hp_boost = t.hp_boost
                um.talent.phy_atk_boost = t.phy_atk_boost
                um.talent.mag_atk_boost = t.mag_atk_boost
                um.talent.phy_def_boost = t.phy_def_boost
                um.talent.mag_def_boost = t.mag_def_boost
                um.talent.spd_boost = t.spd_boost
        else:
            # Add new user_monster
            um = models.UserMonster(
                monster_id=um_data.monster_id,
                personality_id=um_data.personality_id,
                legacy_type_id=um_data.legacy_type_id,
                move1_id=um_data.move1_id,
                move2_id=um_data.move2_id,
                move3_id=um_data.move3_id,
                move4_id=um_data.move4_id,
                team=db_team,
                position=um_data.position
            )
            db.add(um)
            db.flush()
            t = um_data.talent
            talent = models.Talent(
                monster_instance_id=um.id,
                hp_boost=t.hp_boost,
                phy_atk_boost=t.phy_atk_boost,
                mag_atk_boost=t.mag_atk_boost,
                phy_def_boost=t.phy_def_boost,
                mag_def_boost=t.mag_def_boost,
                spd_boost=t.spd_boost,
            )
            db.add(talent)
            um.talent = talent

    db_team.updated_at = func.now()

    # Composition changed → any saved analysis now describes a different team.
    # Delete it so users don't see a stale/wrong analysis for the edited team.
    if new_composition != old_composition:
        stale = (
            db.query(models.TeamAnalysis)
            .filter(models.TeamAnalysis.team_id == team_id)
            .delete(synchronize_session=False)
        )
        if stale:
            logger.info(f"Deleted {stale} stale saved analysis(es) for updated team {team_id}")

    try:
        db.commit()
    except IntegrityError:
        # Bad foreign keys (nonexistent monster/move/personality/type/magic item)
        # are a client error, not a server crash
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Team references a jingling, move, personality, legacy type, or magic item that does not exist"
        )
    db.refresh(db_team)
    return db_team

# -------- DELETE Team --------

@app.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Teams"])
def delete_team(
    team_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a team.

    SECURITY: Only owner can delete.
    """
    db_team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Block deletion of featured teams via the regular endpoint
    if db_team.is_featured:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete a featured team via this endpoint"
        )

    # SECURITY: Check ownership
    if db_team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this team"
        )

    logger.info(f"Deleted team {team_id} for user {current_user.id}")

    db.delete(db_team)
    db.commit()
    return


# ========== ADMIN ENDPOINTS (Phase B) ==========
#
# All admin endpoints require admin privileges.
# Admins are identified by email address via ADMIN_EMAILS env var.


@app.get("/admin/users", response_model=schemas.AdminUserListOut, tags=["Admin"])
async def admin_list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=100),
    tier: Optional[str] = Query(None),
    is_guest: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all users with pagination and filtering.

    ADMIN ONLY: Requires admin privileges.

    Query parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - search: Search by username or email
    - tier: Filter by subscription tier
    - is_guest: Filter by guest status
    - is_active: Filter by active status
    """
    query = db.query(models.User)

    # Apply filters
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (models.User.username.ilike(search_pattern)) |
            (models.User.email.ilike(search_pattern))
        )

    if tier:
        query = query.filter(models.User.subscription_tier == tier)

    if is_guest is not None:
        query = query.filter(models.User.is_guest == is_guest)

    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    users = query.order_by(models.User.created_at.desc()).offset(offset).limit(page_size).all()

    # Build response with additional info
    user_list = []
    for user in users:
        teams_count = db.query(models.Team).filter(models.Team.owner_id == user.id).count()
        analyses_count = (
            db.query(models.TeamAnalysis)
            .join(models.Team, models.TeamAnalysis.team_id == models.Team.id)
            .filter(models.Team.owner_id == user.id)
            .count()
        )
        user_data = schemas.AdminUserOut(
            id=user.id,
            username=user.username,
            email=user.email,
            is_guest=user.is_guest,
            is_system=user.is_system,
            is_active=user.is_active,
            email_verified=user.email_verified,
            subscription_tier=user.subscription_tier,
            subscription_expires_at=user.subscription_expires_at,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            last_active_at=user.last_active_at,
            failed_login_attempts=user.failed_login_attempts,
            locked_until=user.locked_until,
            device_id=user.device_id,
            guest_display_id=user.guest_display_id,
            teams_count=teams_count,
            is_admin=is_admin_user(user),
            analyses_count=analyses_count,
            lock_reason=user.lock_reason,
            registration_ip=user.registration_ip,
            last_login_ip=user.last_login_ip,
            preferred_language=user.preferred_language,
            converted_from_guest=user.converted_from_guest,
        )
        user_list.append(user_data)

    total_pages = (total + page_size - 1) // page_size

    return schemas.AdminUserListOut(
        users=user_list,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@app.get("/admin/users/{user_id}", response_model=schemas.AdminUserOut, tags=["Admin"])
async def admin_get_user(
    user_id: int,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific user.

    ADMIN ONLY: Requires admin privileges.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    teams_count = db.query(models.Team).filter(models.Team.owner_id == user.id).count()
    analyses_count = (
        db.query(models.TeamAnalysis)
        .join(models.Team, models.TeamAnalysis.team_id == models.Team.id)
        .filter(models.Team.owner_id == user.id)
        .count()
    )

    return schemas.AdminUserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        is_guest=user.is_guest,
        is_system=user.is_system,
        is_active=user.is_active,
        email_verified=user.email_verified,
        subscription_tier=user.subscription_tier,
        subscription_expires_at=user.subscription_expires_at,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        last_active_at=user.last_active_at,
        failed_login_attempts=user.failed_login_attempts,
        locked_until=user.locked_until,
        device_id=user.device_id,
        guest_display_id=user.guest_display_id,
        teams_count=teams_count,
        is_admin=is_admin_user(user),
        analyses_count=analyses_count,
        lock_reason=user.lock_reason,
        registration_ip=user.registration_ip,
        last_login_ip=user.last_login_ip,
        preferred_language=user.preferred_language,
        converted_from_guest=user.converted_from_guest,
    )


@app.put("/admin/users/{user_id}/tier", tags=["Admin"])
async def admin_change_tier(
    user_id: int,
    tier_data: schemas.AdminChangeTierRequest,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Change a user's subscription tier.

    ADMIN ONLY: Requires admin privileges.

    Valid tiers: anonymous, guest, free, premium, unlimited
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system user")

    old_tier = user.subscription_tier
    user.subscription_tier = tier_data.tier
    db.commit()

    logger.info(
        f"ADMIN ACTION: User {admin_user.id} ({admin_user.email}) "
        f"changed tier for user {user.id} ({user.username}): {old_tier} -> {tier_data.tier}"
    )

    return {
        "message": f"User tier changed from {old_tier} to {tier_data.tier}",
        "user_id": user.id,
        "old_tier": old_tier,
        "new_tier": tier_data.tier
    }


@app.post("/admin/users/{user_id}/lock", tags=["Admin"])
async def admin_lock_user(
    user_id: int,
    lock_data: schemas.AdminLockUserRequest = None,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lock a user account (disable access).

    ADMIN ONLY: Requires admin privileges.

    Options:
    - duration_hours: Lock for specific duration (optional, default: indefinite)
    - reason: Reason for locking (logged)
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_system:
        raise HTTPException(status_code=400, detail="Cannot lock system user")

    if user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot lock yourself")

    if is_admin_user(user):
        raise HTTPException(status_code=400, detail="Cannot lock another admin")

    # Set lock
    user.is_active = False

    if lock_data and lock_data.duration_hours:
        user.locked_until = datetime.now(timezone.utc) + timedelta(hours=lock_data.duration_hours)
    else:
        user.locked_until = None  # Indefinite lock

    user.lock_reason = lock_data.reason if lock_data and lock_data.reason else None

    # Increment token version to invalidate all sessions
    user.token_version += 1

    db.commit()

    reason = lock_data.reason if lock_data else "No reason provided"
    duration = f"{lock_data.duration_hours} hours" if lock_data and lock_data.duration_hours else "indefinite"

    logger.warning(
        f"ADMIN ACTION: User {admin_user.id} ({admin_user.email}) "
        f"locked user {user.id} ({user.username}). Duration: {duration}. Reason: {reason}"
    )

    return {
        "message": f"User {user.username} has been locked",
        "user_id": user.id,
        "duration": duration,
        "locked_until": user.locked_until
    }


@app.post("/admin/users/{user_id}/unlock", tags=["Admin"])
async def admin_unlock_user(
    user_id: int,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Unlock a user account (restore access).

    ADMIN ONLY: Requires admin privileges.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_active and not user.locked_until:
        return {"message": "User is not locked", "user_id": user.id}

    user.is_active = True
    user.locked_until = None
    user.failed_login_attempts = 0  # Reset failed attempts
    user.lock_reason = None

    db.commit()

    logger.info(
        f"ADMIN ACTION: User {admin_user.id} ({admin_user.email}) "
        f"unlocked user {user.id} ({user.username})"
    )

    return {
        "message": f"User {user.username} has been unlocked",
        "user_id": user.id
    }


@app.delete("/admin/users/{user_id}", tags=["Admin"])
async def admin_delete_user(
    user_id: int,
    delete_data: schemas.AdminDeleteUserRequest = None,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Permanently delete a user account.

    ADMIN ONLY: Requires admin privileges.

    Options:
    - reason: Reason for deletion (logged)
    - add_to_cooldown: Add email to deletion cooldown (default: True)

    WARNING: This action is irreversible. All user data will be deleted.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system user")

    if user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself via admin endpoint")

    if is_admin_user(user):
        raise HTTPException(status_code=400, detail="Cannot delete another admin")

    # Store info for logging
    username = user.username
    email = user.email
    teams_count = db.query(models.Team).filter(models.Team.owner_id == user.id).count()

    # Add to deletion cooldown if requested and user has email
    add_cooldown = delete_data.add_to_cooldown if delete_data else True
    if add_cooldown and email:
        EMAIL_COOLDOWN_DAYS = 30
        deleted_email = models.DeletedEmail(
            email=email.lower(),
            cooldown_until=datetime.now(timezone.utc) + timedelta(days=EMAIL_COOLDOWN_DAYS),
            original_user_id=user.id,
            reason="admin_deleted"
        )
        db.add(deleted_email)

    # Delete user (cascades to teams, user_monsters, talents, analyses)
    db.delete(user)
    db.commit()

    reason = delete_data.reason if delete_data else "No reason provided"

    logger.warning(
        f"ADMIN ACTION: User {admin_user.id} ({admin_user.email}) "
        f"deleted user {user_id} ({username}, {email}). "
        f"Teams deleted: {teams_count}. Reason: {reason}"
    )

    return {
        "message": f"User {username} has been permanently deleted",
        "user_id": user_id,
        "teams_deleted": teams_count,
        "email_cooldown_added": add_cooldown and email is not None
    }


@app.post("/admin/featured-teams", response_model=schemas.TeamOut, tags=["Admin"])
async def admin_create_featured_team(
    team: schemas.TeamCreate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Create a new featured team (admin-curated).

    ADMIN ONLY: Team is owned by the system user and marked as featured.
    Featured teams appear in the Quick Build pool for all users.
    """
    system_user = db.query(models.User).filter(models.User.is_system == True).first()
    if not system_user:
        raise HTTPException(status_code=500, detail="System user not found. Cannot create featured team.")

    # Case-insensitive name uniqueness among featured teams
    existing = db.query(models.Team).filter(
        models.Team.is_featured == True,
        func.lower(models.Team.name) == func.lower(team.name)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A featured team named '{team.name}' already exists"
        )

    db_team = models.Team(
        name=team.name,
        magic_item_id=team.magic_item_id,
        owner_id=system_user.id,
        is_featured=True
    )
    db.add(db_team)
    db.flush()

    for um in team.user_monsters:
        db_um = models.UserMonster(
            monster_id=um.monster_id,
            personality_id=um.personality_id,
            legacy_type_id=um.legacy_type_id,
            move1_id=um.move1_id,
            move2_id=um.move2_id,
            move3_id=um.move3_id,
            move4_id=um.move4_id,
            team_id=db_team.id,
            position=um.position
        )
        db.add(db_um)
        db.flush()
        db_talent = models.Talent(
            monster_instance_id=db_um.id,
            hp_boost=um.talent.hp_boost,
            phy_atk_boost=um.talent.phy_atk_boost,
            mag_atk_boost=um.talent.mag_atk_boost,
            phy_def_boost=um.talent.phy_def_boost,
            mag_def_boost=um.talent.mag_def_boost,
            spd_boost=um.talent.spd_boost
        )
        db.add(db_talent)
        db_um.talent = db_talent
    db.commit()
    db.refresh(db_team)

    # Invalidate featured teams cache
    await redis_cache.delete("featured_teams:list")

    logger.info(f"ADMIN ACTION: {admin_user.email} created featured team {db_team.id} '{db_team.name}'")
    return db_team


@app.put("/admin/featured-teams/{team_id}", response_model=schemas.TeamOut, tags=["Admin"])
async def admin_update_featured_team(
    team_id: int,
    team_update: schemas.TeamUpdate,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Update an existing featured team.

    ADMIN ONLY: Can update name, magic item, and all 6 monsters.
    """
    db_team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not db_team or not db_team.is_featured:
        raise HTTPException(status_code=404, detail="Featured team not found")

    # Case-insensitive name uniqueness, excluding self
    if team_update.name is not None:
        existing = db.query(models.Team).filter(
            models.Team.is_featured == True,
            models.Team.id != team_id,
            func.lower(models.Team.name) == func.lower(team_update.name)
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A featured team named '{team_update.name}' already exists"
            )
        db_team.name = team_update.name

    if team_update.magic_item_id is not None:
        db_team.magic_item_id = team_update.magic_item_id

    # Upsert user_monsters (same logic as PUT /teams/{team_id})
    incoming_by_id = {um.id: um for um in team_update.user_monsters if um.id is not None}
    incoming_ids = set(incoming_by_id.keys())

    for db_um in list(db_team.user_monsters):
        if db_um.id not in incoming_ids:
            db.delete(db_um)
    db.flush()

    existing_ums = {um.id: um for um in db_team.user_monsters}

    for um_data in team_update.user_monsters:
        if um_data.id is not None and um_data.id in existing_ums:
            um = existing_ums[um_data.id]
            um.monster_id = um_data.monster_id
            um.personality_id = um_data.personality_id
            um.legacy_type_id = um_data.legacy_type_id
            um.move1_id = um_data.move1_id
            um.move2_id = um_data.move2_id
            um.move3_id = um_data.move3_id
            um.move4_id = um_data.move4_id
            um.position = um_data.position
            if um.talent:
                t = um_data.talent
                um.talent.hp_boost = t.hp_boost
                um.talent.phy_atk_boost = t.phy_atk_boost
                um.talent.mag_atk_boost = t.mag_atk_boost
                um.talent.phy_def_boost = t.phy_def_boost
                um.talent.mag_def_boost = t.mag_def_boost
                um.talent.spd_boost = t.spd_boost
        else:
            um = models.UserMonster(
                monster_id=um_data.monster_id,
                personality_id=um_data.personality_id,
                legacy_type_id=um_data.legacy_type_id,
                move1_id=um_data.move1_id,
                move2_id=um_data.move2_id,
                move3_id=um_data.move3_id,
                move4_id=um_data.move4_id,
                team=db_team,
                position=um_data.position
            )
            db.add(um)
            db.flush()
            t = um_data.talent
            talent = models.Talent(
                monster_instance_id=um.id,
                hp_boost=t.hp_boost,
                phy_atk_boost=t.phy_atk_boost,
                mag_atk_boost=t.mag_atk_boost,
                phy_def_boost=t.phy_def_boost,
                mag_def_boost=t.mag_def_boost,
                spd_boost=t.spd_boost
            )
            db.add(talent)
            um.talent = talent

    db_team.updated_at = func.now()
    db.commit()
    db.refresh(db_team)

    # Invalidate featured teams cache
    await redis_cache.delete("featured_teams:list")

    logger.info(f"ADMIN ACTION: {admin_user.email} updated featured team {team_id}")
    return db_team


@app.delete("/admin/featured-teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin"])
async def admin_delete_featured_team(
    team_id: int,
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a featured team.

    ADMIN ONLY: Cascades to user_monsters, talent, and analyses.
    """
    db_team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not db_team or not db_team.is_featured:
        raise HTTPException(status_code=404, detail="Featured team not found")

    db.delete(db_team)
    db.commit()

    # Invalidate featured teams cache
    await redis_cache.delete("featured_teams:list")

    logger.info(f"ADMIN ACTION: {admin_user.email} deleted featured team {team_id}")
    return


@app.get("/admin/stats", response_model=schemas.AdminStatsOut, tags=["Admin"])
async def admin_get_stats(
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get system-wide statistics.

    ADMIN ONLY: Requires admin privileges.

    Returns counts for users, teams, analyses, and registration trends.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    # User counts
    total_users = db.query(models.User).count()
    total_guests = db.query(models.User).filter(models.User.is_guest == True).count()
    total_registered = db.query(models.User).filter(
        models.User.is_guest == False,
        models.User.is_system == False
    ).count()
    total_active = db.query(models.User).filter(
        models.User.last_active_at >= thirty_days_ago
    ).count()
    total_locked = db.query(models.User).filter(models.User.is_active == False).count()

    # Team and analysis counts
    total_teams = db.query(models.Team).count()
    total_featured_teams = db.query(models.Team).filter(models.Team.is_featured == True).count()
    total_analyses = db.query(models.TeamAnalysis).count()

    # Analysis trends
    analyses_today = db.query(models.TeamAnalysis).filter(
        models.TeamAnalysis.created_at >= today_start
    ).count()
    analyses_this_week = db.query(models.TeamAnalysis).filter(
        models.TeamAnalysis.created_at >= week_start
    ).count()
    analyses_this_month = db.query(models.TeamAnalysis).filter(
        models.TeamAnalysis.created_at >= month_start
    ).count()

    # Guest conversion tracking
    guest_conversions = db.query(models.User).filter(
        models.User.converted_from_guest == True,
        models.User.is_guest == False,
        models.User.is_system == False
    ).count()

    # Users by tier
    tier_counts = db.query(
        models.User.subscription_tier,
        func.count(models.User.id)
    ).group_by(models.User.subscription_tier).all()
    users_by_tier = {tier: count for tier, count in tier_counts}

    # Registration trends
    registrations_today = db.query(models.User).filter(
        models.User.created_at >= today_start,
        models.User.is_guest == False,
        models.User.is_system == False
    ).count()

    registrations_this_week = db.query(models.User).filter(
        models.User.created_at >= week_start,
        models.User.is_guest == False,
        models.User.is_system == False
    ).count()

    registrations_this_month = db.query(models.User).filter(
        models.User.created_at >= month_start,
        models.User.is_guest == False,
        models.User.is_system == False
    ).count()

    return schemas.AdminStatsOut(
        total_users=total_users,
        total_guests=total_guests,
        total_registered=total_registered,
        total_active=total_active,
        total_locked=total_locked,
        total_teams=total_teams,
        total_featured_teams=total_featured_teams,
        total_analyses=total_analyses,
        users_by_tier=users_by_tier,
        registrations_today=registrations_today,
        registrations_this_week=registrations_this_week,
        registrations_this_month=registrations_this_month,
        analyses_today=analyses_today,
        analyses_this_week=analyses_this_week,
        analyses_this_month=analyses_this_month,
        guest_conversions=guest_conversions,
    )


@app.post("/admin/database/reset-users", tags=["Admin"])
async def admin_reset_users(
    admin_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    DEV ONLY: Delete all non-admin, non-system users.

    ADMIN ONLY: Requires admin privileges.

    WARNING: This is a destructive operation for testing purposes.
    Only available when ENVIRONMENT != 'production'.

    This will:
    - Delete all guest users
    - Delete all registered users (except admins)
    - Delete all teams owned by deleted users
    - Clear deleted_emails table
    - NOT delete admin users or system user
    """
    if ENVIRONMENT == "production":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is disabled in production"
        )

    from backend.config import ADMIN_EMAILS

    # Find users to delete (not system, not admin).
    # Guests have email IS NULL, for which `~email.in_(...)` evaluates to SQL
    # NULL (excluded) — include them explicitly so guest rows are actually reset.
    users_to_delete = db.query(models.User).filter(
        models.User.is_system == False,
        or_(models.User.email.is_(None), ~models.User.email.in_(ADMIN_EMAILS)) if ADMIN_EMAILS else True
    ).all()

    deleted_count = 0
    teams_deleted = 0

    for user in users_to_delete:
        # Skip if user is admin
        if is_admin_user(user):
            continue

        # Count teams
        user_teams = db.query(models.Team).filter(models.Team.owner_id == user.id).count()
        teams_deleted += user_teams

        db.delete(user)
        deleted_count += 1

    # Clear deleted_emails
    cooldowns_cleared = db.query(models.DeletedEmail).delete()

    db.commit()

    # Reset sequence if all non-system users deleted
    remaining = db.query(models.User).filter(models.User.is_system == False).count()
    if remaining == 0:
        db.execute(text("SELECT setval('users_id_seq', 1, false)"))
        db.commit()

    logger.warning(
        f"ADMIN ACTION: User {admin_user.id} ({admin_user.email}) "
        f"reset users database. Deleted: {deleted_count} users, {teams_deleted} teams, "
        f"{cooldowns_cleared} email cooldowns"
    )

    return {
        "message": "User database reset complete",
        "users_deleted": deleted_count,
        "teams_deleted": teams_deleted,
        "email_cooldowns_cleared": cooldowns_cleared
    }


# ========== FEEDBACK ==========

@app.post("/feedback", tags=["Feedback"])
@limiter.limit("3/day")
async def submit_feedback(
    request: Request,
    data: schemas.FeedbackRequest,
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    """
    Submit user feedback or bug report.

    - Rate limited: 3 submissions per IP per day
    - Open to all users (anonymous, guest, registered)
    - Honeypot field silently discards bot submissions
    - Sends email to all ADMIN_EMAILS via existing SMTP config
    """
    # Honeypot: bots fill hidden fields, humans don't see them
    if data.website:
        return {"message": "Feedback received."}

    if not ADMIN_EMAILS:
        logger.warning("No ADMIN_EMAILS configured — feedback not delivered")
        return {"message": "Feedback received."}

    ip = get_real_client_ip(request)
    if current_user:
        email_display = current_user.email or "—"
        user_type = "Guest" if current_user.is_guest else "Registered"
        user_info = f"{user_type}: {current_user.username} (id={current_user.id}, email={email_display})"
    else:
        user_info = "Anonymous"

    category_display = data.category.title()
    reply_line = f"<p><strong>Reply to:</strong> {data.reply_email}</p>" if data.reply_email else "<p><em>No reply email provided.</em></p>"

    subject = f"[RK Feedback] {category_display} — {user_info[:60]}"
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
      <h2 style="color: #1d4ed8; margin-bottom: 4px;">RK Team Builder — New Feedback</h2>
      <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 12px 0;" />
      <p><strong>Category:</strong> {category_display}</p>
      <p><strong>Submitted by:</strong> {user_info}</p>
      <p><strong>IP:</strong> {ip}</p>
      {reply_line}
      <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 12px 0;" />
      <p><strong>Message:</strong></p>
      <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; white-space: pre-wrap; font-size: 15px; line-height: 1.6;">
        {data.message}
      </div>
    </div>
    """
    text_body = f"[RK Feedback] {category_display}\n\nFrom: {user_info}\nIP: {ip}\nReply to: {data.reply_email or 'N/A'}\n\n{data.message}"

    for admin_email in ADMIN_EMAILS:
        await send_email(admin_email, subject, html_body, text_body)

    logger.info(f"Feedback submitted: category={data.category}, from={user_info}")
    return {"message": "Feedback received."}


# ─────────────────────────────────────────────────────────────────────────────
# Share
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/share/decode", response_model=schemas.ShareDecodeResponse, tags=["Share"])
@limiter.limit("30/minute")
async def decode_share(request: Request, t: str, db: Session = Depends(get_db)):
    """
    Decode a base64url team share payload and resolve all IDs to full objects.

    - No authentication required
    - Rate limited: 30 requests/minute per IP
    - Returns 422 for invalid payloads or removed game data
    """
    import base64, json as _json

    # Guard against absurdly large payloads before any DB work
    if len(t) > 2048:
        raise HTTPException(status_code=422, detail="Invalid share link format")

    # Decode base64url → UTF-8 string → JSON
    try:
        padded = t + '=' * (-len(t) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(padded).decode('utf-8'))
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid share link format")

    # Structural validation
    try:
        if not isinstance(payload, dict):
            raise ValueError
        monsters_raw = payload.get("m", [])
        if (
            payload.get("v") != 1
            or not isinstance(payload.get("n"), str)
            or not isinstance(payload.get("mi"), int)
            or not isinstance(monsters_raw, list)
            or len(monsters_raw) != 6
        ):
            raise ValueError
        for m_data in monsters_raw:
            if not isinstance(m_data, dict):
                raise ValueError
            mv = m_data.get("mv", [])
            if (
                not isinstance(m_data.get("id"), int)
                or not isinstance(m_data.get("p"), int)
                or not isinstance(m_data.get("lt"), int)
                or not isinstance(mv, list)
                or len(mv) != 4
                or not all(isinstance(x, int) for x in mv)
            ):
                raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid share link format")

    # Talent validation — prevents 500 from Pydantic model_validator on crafted payloads
    allowed_boosts = {0, 7, 8, 9, 10}
    for m_data in monsters_raw:
        t_vals = m_data.get("t", [])
        if not isinstance(t_vals, list) or len(t_vals) != 6:
            raise HTTPException(status_code=422, detail="Invalid share link format")
        if not all(isinstance(v, int) and v in allowed_boosts for v in t_vals):
            raise HTTPException(status_code=422, detail="Invalid share link format")
        non_zero = sum(1 for v in t_vals if v != 0)
        if non_zero < 1:
            raise HTTPException(status_code=422, detail="Invalid share link format")

    team_name = str(payload["n"]).strip()[:16]
    shared_by: Optional[str] = str(payload["u"]).strip()[:32] if payload.get("u") else None
    note: Optional[str] = str(payload["no"]).strip()[:150] if payload.get("no") else None
    magic_item_id: int = payload["mi"]

    # Resolve magic item
    magic_item = db.query(models.MagicItem).filter(models.MagicItem.id == magic_item_id).first()
    if not magic_item:
        raise HTTPException(status_code=422, detail="This team references game data that is no longer available")

    resolved_monsters: list[schemas.SharedMonsterData] = []

    for m_data in monsters_raw:
        monster_id: int = m_data["id"]
        personality_id: int = m_data["p"]
        legacy_type_id: int = m_data["lt"]
        move_ids: list[int] = m_data["mv"]
        t_vals: list[int] = m_data["t"]

        # Resolve monster
        monster = db.query(models.Monster).filter(models.Monster.id == monster_id).first()
        if not monster:
            raise HTTPException(status_code=422, detail="This team references game data that is no longer available")

        # Resolve personality
        personality = db.query(models.Personality).filter(models.Personality.id == personality_id).first()
        if not personality:
            raise HTTPException(status_code=422, detail="This team references game data that is no longer available")

        # Resolve legacy type
        legacy_type = db.query(models.Type).filter(models.Type.id == legacy_type_id).first()
        if not legacy_type:
            raise HTTPException(status_code=422, detail="This team references game data that is no longer available")

        # Build valid move-ID sets (pool + stones + legacy)
        move_pool_ids = {m.id for m in monster.move_pool}
        move_stone_ids = {m.id for m in monster.move_stones}
        legacy_move_ids = {
            lm.move_id
            for lm in db.query(models.LegacyMove).filter(models.LegacyMove.monster_id == monster.id).all()
        }
        all_valid_ids = move_pool_ids | move_stone_ids | legacy_move_ids

        # Resolve each move; flag validity
        resolved_moves: list[Optional[models.Move]] = []
        move_valid: list[bool] = []
        for mid in move_ids:
            move_obj = db.query(models.Move).filter(models.Move.id == mid).first()
            if move_obj is None:
                # Move deleted from DB entirely
                raise HTTPException(status_code=422, detail="This team references game data that is no longer available")
            resolved_moves.append(move_obj)
            move_valid.append(mid in all_valid_ids)

        talent = schemas.TalentOut(
            id=0,  # synthetic sentinel — not a real DB talent ID
            hp_boost=t_vals[0],
            phy_atk_boost=t_vals[1],
            mag_atk_boost=t_vals[2],
            phy_def_boost=t_vals[3],
            mag_def_boost=t_vals[4],
            spd_boost=t_vals[5],
        )

        resolved_monsters.append(schemas.SharedMonsterData(
            monster=schemas.MonsterLiteOut.model_validate(monster),
            personality=schemas.PersonalityOut.model_validate(personality),
            legacy_type=schemas.TypeOut.model_validate(legacy_type),
            moves=[schemas.MoveOut.model_validate(m) for m in resolved_moves],
            talent=talent,
            move_valid=move_valid,
        ))

    invalid_count = sum(1 for m in resolved_monsters for v in m.move_valid if not v)
    logger.info(f"Share decoded: team='{team_name}' shared_by={shared_by!r} invalid_moves={invalid_count}")

    return schemas.ShareDecodeResponse(
        team_name=team_name,
        shared_by=shared_by,
        note=note,
        magic_item=schemas.MagicItemOut.model_validate(magic_item),
        monsters=resolved_monsters,
    )
