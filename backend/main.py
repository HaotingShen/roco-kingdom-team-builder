from fastapi import FastAPI, Depends, Query, HTTPException, status, Request, Response, Cookie, Body
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.orm import Session, sessionmaker, joinedload
from sqlalchemy import create_engine, or_, cast, String, func, text
from backend.config import (
    DATABASE_URL,
    LLM_PROVIDER,
    ALLOWED_ORIGINS,
    LOG_LEVEL,
    DB_POOL_SIZE,
    DB_MAX_OVERFLOW,
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
)
from typing import Optional, List, Literal
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from backend import models, schemas
from backend.cache import llm_cache, RedisCache
from backend.rate_limiter import (
    limiter,
    analysis_rate_limit,
    rate_limit_exceeded_handler,
    check_analysis_rate_limit_async,
    check_global_ip_rate_limit_async,
    record_analysis_async,
    get_rate_limit_message,
    get_real_client_ip,
)
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from collections import Counter
import re
import asyncio
import json
import time
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
)
from backend.email_service import (
    send_verification_email,
    send_password_reset_email,
    send_email_change_verification,
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

应对关系：防御类技能自带应对攻击（应对成功获得先手+1）；部分状态类技能带应对防御（应对成功返还能量）；部分攻击类技能带应对状态（应对成功威力+50%）。这形成克制三角，预测对手技能类别选择应对是PvP关键策略。

增益指提升攻击、防御、速度、技能威力、连击数、吸血或降低技能能耗；减益相反。技能中的"全技能威力/全技能能耗"影响该精灵当前所有技能。精灵离场时清除非永久性增减益和大多数状态效果（印记除外）。

层数定义：当"层数"用于增益/减益时，以10为换算基准。百分比增减：每10% = 1层，如物攻+150% = +15层物攻。数值增减（非百分比且为10的倍数）：每10点 = 1层，如技能威力+20 = +2层技能威力。当"层数"用于状态/印记时，层数按状态本身叠加规则计算，不做上述换算。

冷却定义：技能或血脉魔法在再次使用前必须经过的回合数。除非另有说明，所有防御类技能的冷却为1回合，而其他类别的技能通常没有冷却；血脉魔法中"愿力强化"的冷却为3回合，而其他血脉魔法为每场一次性使用。

在进行队伍与精灵分析时，请默认对战结算遵循以上关于魔力值、力竭、能量、技能类别、应对系统、增减益、迅捷、先手与速度、层数定义、冷却定义及血脉魔法的规则。"""

BATTLE_MECHANICS_EN = """Each player brings 6 monsters into battle. Each monster has 6 stats (HP, Physical Attack, Magic Attack, Physical Defense, Magic Defense, Speed). In battle, each monster can only carry 4 moves. In move descriptions, "Attack" affects both Physical and Magic Attack; "Defense" affects both Physical and Magic Defense.

At battle start, each player has 4 Life Points. Only 1 monster per side can be on the field at once. When a monster is defeated, the player loses 1 Life Point (some traits alter this). When Life Points reach 0, that player loses. After defeat, manually select a new monster to enter.

Each monster starts with 10 energy (some traits affect initial energy). Energy is tracked per monster. Using moves consumes their marked energy cost.

Each turn, both players simultaneously choose one action: (1) Use a move: select 1 of 4 moves and pay its energy cost; (2) Focus: skip this turn, restore 5 energy (classified as Status-type move); (3) Actively switch monsters. Magic Item does not count as an action. If available this turn, it may be used at any time without consuming an action or energy, and it takes effect before your chosen action resolves.

Active switching executes before all move resolutions. When a monster enters via active switch, if it has any move with "Quick Entry" effect and enough energy to use it, it immediately and automatically uses the first eligible Quick Entry move in moveset slot order. Quick Entry only triggers on active switch-in, not passive entry.

All moves fall into three categories: Attack-type (Physical/Magic Attack), Defense-type, Status-type. A "Counter" system exists: if the opponent's move category matches this move's counterable category, counter succeeds and this move resolves immediately with highest priority, ignoring speed order. Both sides cannot counter simultaneously. Without counter triggers, turn order is determined by priority value; if equal, higher speed acts first. Active switching always executes before move resolution.

Counter relationships: All Defense moves have Counter Attack (successful counter grants Priority +1 next turn); some Status moves have Counter Defense (successful counter refunds energy cost); some Attack moves have Counter Status (successful counter grants +50% power). This forms a counter triangle—predicting opponent's move category to select counters is key PvP strategy.

Buffs increase Attack, Defense, Speed, move power, Combo count, Lifesteal, or decrease move energy cost; Debuffs do the opposite. "All Move Power/Move Energy Cost" affects all moves currently carried by that monster. When monsters leave the field, non-permanent buffs/debuffs and most of status effects are removed (except marks).

Stack definition: When "stacks" are used for buffs/debuffs, convert using 10 as the base unit. For percentage changes, every 10% = 1 stack (e.g., Physical Attack +150% = +15 stacks of Physical Attack). For flat value changes (non-percentage and a multiple of 10), every 10 points = 1 stack (e.g., Move Power +20 = +2 stacks of Move Power). When "stacks" refer to status/mark effects, stacks follow their own stacking rules and do not use the above conversion.

Cooldown definition: The number of turns that must pass before a move or magic item can be used again. Unless otherwise specified, all Defense-type moves have a 1-turn cooldown, while moves of other categories have no cooldown. For magic items, "Willpower Enhancement" has a 3-turn cooldown, while other magic item effects are single-use per battle.

When performing monster and team analysis, assume battle resolution follows the above rules regarding Life Points, defeated state, energy, move categories, counter system, buffs/debuffs, Quick Entry, priority and speed, stack definitions, cooldown definitions, and Magic Items."""

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

# Initialize Redis cache
redis_cache = RedisCache(
    redis_url=REDIS_URL,
    ttl_seconds=REDIS_CACHE_TTL,
    lock_timeout=REDIS_LOCK_TIMEOUT,
    lock_blocking_timeout=REDIS_LOCK_BLOCKING_TIMEOUT,
)


@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    logger.info("Application startup: connecting to Redis...")
    await redis_cache.connect()
    await revocation_service.connect()


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

engine = create_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
        guest_display_id=user.guest_display_id
    )

# Compute effective stats with base, talent, and personality multipliers
def round_half_up(n):
    return int(Decimal(n).to_integral_value(rounding=ROUND_HALF_UP))

def compute_effective_stats(monster, personality, talent):
    # New formula (Beta Test 3):
    # Roco coefficient: L = (base_stat + (talent × 6)/2) / 100
    # HP: initial_hp = (2L + 1) * 60 + 50L + 10 = 170L + 70
    #     final_hp = initial_hp * (1 + personality_modifier) + 50
    # Other stats: initial_stat = L * 60 + 50L + 10 = 110L + 10
    #              final_stat = initial_stat * (1 + personality_modifier) + 50

    base_hp = monster.base_hp
    hp_talent = talent.hp_boost
    L_hp = (base_hp + (hp_talent * 6) / 2) / 100
    initial_hp = 170 * L_hp + 70
    final_hp = initial_hp * (1 + personality.hp_mod_pct) + 50
    hp = int(round_half_up(final_hp))

    def other_stat(attr, personality_attr, talent_attr):
        base = getattr(monster, attr)
        pers = getattr(personality, personality_attr)
        tal = getattr(talent, talent_attr)
        L = (base + (tal * 6) / 2) / 100
        initial = 110 * L + 10
        final = initial * (1 + pers) + 50
        return int(round_half_up(final))

    return schemas.EffectiveStats(
        hp=hp,
        phy_atk=other_stat("base_phy_atk", "phy_atk_mod_pct", "phy_atk_boost"),
        mag_atk=other_stat("base_mag_atk", "mag_atk_mod_pct", "mag_atk_boost"),
        phy_def=other_stat("base_phy_def", "phy_def_mod_pct", "phy_def_boost"),
        mag_def=other_stat("base_mag_def", "mag_def_mod_pct", "mag_def_boost"),
        spd=other_stat("base_spd", "spd_mod_pct", "spd_boost"),
    )
    
# Compute energy profile for moves, including average cost, zero-cost moves, and energy restore moves
def compute_energy_profile(moves):
    # moves: list of 4 move SQLAlchemy objects, each with .energy_cost
    costs = [getattr(m, "energy_cost", None) for m in moves if m is not None]
    costs = [c for c in costs if c is not None]

    avg_cost = sum(costs) / len(costs) if costs else 0.0
    zero_cost_moves = [m.id for m in moves if m and getattr(m, "energy_cost", None) == 0]
    has_zero_cost = len(zero_cost_moves) > 0

    # Energy restore pattern
    energy_patterns = [
        r"gain[s]? \w+ energy",
        r"restore[s]? \w+ energy",
        r"steal[s]? \w+ energy",
        r"gain[s]? energy",
        r"restore[s]? energy"
    ]
    combined_pattern = re.compile("|".join(energy_patterns), flags=re.IGNORECASE)

    energy_restore_moves = [
        m.id for m in moves
        if m and hasattr(m, "description") and m.description and combined_pattern.search(m.description)
    ]
    has_energy_restore = len(energy_restore_moves) > 0

    return schemas.EnergyProfile(
        avg_energy_cost=round(avg_cost, 2),
        has_zero_cost_move=has_zero_cost,
        has_energy_restore_move=has_energy_restore,
        zero_cost_moves=zero_cost_moves,
        energy_restore_moves=energy_restore_moves
    )

def resolve_dynamic_move_properties(move, user_monster, monster, personality, talent, type_db_map):
    """
    Resolve dynamic properties for special moves like Willpower Impact.

    Returns dict with 'type' and 'category' (resolved or original values).
    """
    # Check if this is Willpower Impact (the only dynamic move currently)
    if move.name != "Willpower Impact":
        return {'type': move.move_type, 'category': move.move_category}

    # Resolve type: Use user's legacy type (stored as null)
    resolved_type = type_db_map.get(user_monster.legacy_type_id)

    # Resolve category: Based on effective stats comparison
    effective_stats = compute_effective_stats(monster, personality, talent)
    resolved_category = (models.MoveCategory.PHY_ATTACK
                        if effective_stats.phy_atk > effective_stats.mag_atk
                        else models.MoveCategory.MAG_ATTACK)

    return {'type': resolved_type, 'category': resolved_category}

# Compute counter coverage for moves with attack/defense/status counters
def compute_counter_coverage(moves):
    # moves: list of 4 move SQLAlchemy objects, each with .move_category and .has_counter
    has_attack_counter_status = False
    has_defense_counter_attack = False
    has_status_counter_defense = False
    counter_move_ids = []

    for m in moves:
        if not m or not getattr(m, "has_counter", False):
            continue
        counter_move_ids.append(m.id)
        cat = getattr(m, "move_category", None)
        if cat in [models.MoveCategory.PHY_ATTACK, models.MoveCategory.MAG_ATTACK]:
            has_attack_counter_status = True
        elif cat == models.MoveCategory.DEFENSE:
            has_defense_counter_attack = True
        elif cat == models.MoveCategory.STATUS:
            has_status_counter_defense = True
        
    return schemas.CounterCoverage(
        has_attack_counter_status=has_attack_counter_status,
        has_defense_counter_attack=has_defense_counter_attack,
        has_status_counter_defense=has_status_counter_defense,
        total_counter_moves=len(counter_move_ids),
        counter_move_ids=counter_move_ids
    )
    
# Count and record defense/status moves
def compute_defense_status_move(moves):
    defense_status_move_ids = []
    for m in moves:
        if m.move_category in [models.MoveCategory.DEFENSE, models.MoveCategory.STATUS]:
            defense_status_move_ids.append(m.id)
    return schemas.DefenseStatusMove(
        defense_status_move_count=len(defense_status_move_ids),
        defense_status_move=defense_status_move_ids,
    )
    
# Trait Synergy LLM Analysis
def get_localized_name(entity, language="en"):
    """Extract localized name from entity's localized field, falling back to English name."""
    # Get fallback name (GameTerm uses 'key' instead of 'name')
    fallback_name = getattr(entity, "name", None) or getattr(entity, "key", str(entity))

    if hasattr(entity, "localized") and entity.localized:
        try:
            if language == "zh" and "zh" in entity.localized:
                zh_data = entity.localized["zh"]
                if isinstance(zh_data, dict):
                    return zh_data.get("name", fallback_name)
                # If zh_data is a string, it might be the name itself
                elif isinstance(zh_data, str):
                    return zh_data
            if "en" in entity.localized:
                en_data = entity.localized["en"]
                if isinstance(en_data, dict):
                    return en_data.get("name", fallback_name)
                elif isinstance(en_data, str):
                    return en_data
        except (KeyError, TypeError, AttributeError):
            pass
    return fallback_name

def get_localized_description(entity, language="en"):
    """Extract localized description from entity's localized field, falling back to English description."""
    if hasattr(entity, "localized") and entity.localized:
        try:
            if language == "zh" and "zh" in entity.localized:
                zh_data = entity.localized["zh"]
                if isinstance(zh_data, dict):
                    return zh_data.get("description", getattr(entity, "description", ""))
            if "en" in entity.localized:
                en_data = entity.localized["en"]
                if isinstance(en_data, dict):
                    return en_data.get("description", getattr(entity, "description", ""))
        except (KeyError, TypeError, AttributeError):
            pass
    return getattr(entity, "description", "")

def get_localized_move_category(move_category, language="en"):
    """Convert MoveCategory enum/string to localized string representation."""
    category_map = {
        "en": {
            "PHY_ATTACK": "Physical Attack",
            "MAG_ATTACK": "Magic Attack",
            "DEFENSE": "Defense",
            "STATUS": "Status"
        },
        "zh": {
            "PHY_ATTACK": "物攻",
            "MAG_ATTACK": "魔攻",
            "DEFENSE": "防御",
            "STATUS": "状态"
        }
    }

    if not move_category:
        return "Unknown" if language == "en" else "未知"

    # Handle enum object
    if hasattr(move_category, 'name'):
        category_key = move_category.name
    # Handle string (from database/API)
    elif isinstance(move_category, str):
        # Map string values to enum names
        string_to_enum = {
            "Physical Attack": "PHY_ATTACK",
            "Magic Attack": "MAG_ATTACK",
            "Status": "STATUS",
            "Defense": "DEFENSE"
        }
        category_key = string_to_enum.get(move_category, None)
    else:
        category_key = None

    if category_key:
        return category_map.get(language, category_map["en"]).get(category_key, "Unknown" if language == "en" else "未知")
    return "Unknown" if language == "en" else "未知"

def build_trait_synergy_prompt(monster, trait, selected_moves, game_terms, referenced_moves, referenced_monsters, main_type, sub_type, type_db_map, language="en"):
    # Use localized names and descriptions
    monster_name = get_localized_name(monster, language)
    trait_name = get_localized_name(trait, language)
    trait_desc = get_localized_description(trait, language)

    # Build type information
    main_type_name = get_localized_name(main_type, language)
    type_info = main_type_name
    if sub_type:
        sub_type_name = get_localized_name(sub_type, language)
        type_info = f"{main_type_name}/{sub_type_name}"

    # Build complete type effectiveness table for all types
    type_chart_lines = []
    # Get all types and sort them by name for consistency
    all_types = sorted(type_db_map.values(), key=lambda t: get_localized_name(t, language))

    for t in all_types:
        type_name = get_localized_name(t, language)
        # Skip "Leader" or other special types that aren't real battle types
        if type_name in ["Leader", "首领"]:
            continue

        effective = []
        weak = []

        if hasattr(t, 'effective_against') and t.effective_against:
            effective = sorted([get_localized_name(target, language) for target in t.effective_against])
        if hasattr(t, 'weak_against') and t.weak_against:
            weak = sorted([get_localized_name(target, language) for target in t.weak_against])

        if language == "zh":
            eff_str = ', '.join(effective) if effective else '无'
            weak_str = ', '.join(weak) if weak else '无'
            type_chart_lines.append(f"  {type_name} → 克制: {eff_str} | 效果不佳: {weak_str}")
        else:
            eff_str = ', '.join(effective) if effective else 'None'
            weak_str = ', '.join(weak) if weak else 'None'
            type_chart_lines.append(f"  {type_name} → Effective Against: {eff_str} | Weak Against: {weak_str}")

    type_chart = "\n".join(type_chart_lines)

    # Build move information with type, category, energy cost, and power
    move_lines = []
    for m in selected_moves:
        move_name = get_localized_name(m, language)
        move_desc = get_localized_description(m, language)
        move_type_name = get_localized_name(m.move_type, language) if m.move_type else "None"
        move_category_str = get_localized_move_category(m.move_category, language)
        energy_cost = getattr(m, 'energy_cost', 'N/A')
        power_str = str(m.power) if m.power is not None else "-"

        if language == "zh":
            move_lines.append(f"- {move_name} (系别：{move_type_name}, 类别：{move_category_str}, 能量消耗:{energy_cost}, 威力:{power_str}): {move_desc}")
        else:
            move_lines.append(f"- {move_name} (Type: {move_type_name}, Category: {move_category_str}, Energy Cost:{energy_cost}, Power:{power_str}): {move_desc}")
    move_lines_str = "\n".join(move_lines)
    glossary = "\n".join(
        f"- {get_localized_name(gt, language)}: {get_localized_description(gt, language)}" for gt in game_terms
    )

    # Build referenced moves section (moves mentioned in trait/move descriptions)
    referenced_moves_section = ""
    if referenced_moves:
        ref_move_lines = []
        for m in referenced_moves:
            move_name = get_localized_name(m, language)
            move_desc = get_localized_description(m, language)
            move_type_name = get_localized_name(m.move_type, language) if m.move_type else "None"
            move_category_str = get_localized_move_category(m.move_category, language)
            energy_cost = getattr(m, 'energy_cost', 'N/A')
            power_str = str(m.power) if m.power is not None else "-"

            if language == "zh":
                ref_move_lines.append(f"- {move_name} (系别：{move_type_name}, 类别：{move_category_str}, 能量消耗:{energy_cost}, 威力:{power_str}): {move_desc}")
            else:
                ref_move_lines.append(f"- {move_name} (Type: {move_type_name}, Category: {move_category_str}, Energy Cost:{energy_cost}, Power:{power_str}): {move_desc}")
        referenced_moves_section = "\n".join(ref_move_lines)

    # Build referenced monsters section (monsters mentioned in trait/move descriptions)
    referenced_monsters_section = ""
    if referenced_monsters:
        ref_monster_lines = []
        for mon in referenced_monsters:
            mon_name = get_localized_name(mon, language)
            mon_main_type = type_db_map[mon.main_type_id]
            mon_type_str = get_localized_name(mon_main_type, language)
            if mon.sub_type_id:
                mon_sub_type = type_db_map[mon.sub_type_id]
                mon_type_str = f"{mon_type_str}/{get_localized_name(mon_sub_type, language)}"

            # Get trait information
            mon_trait = trait_db_map[mon.trait_id]
            mon_trait_name = get_localized_name(mon_trait, language)
            mon_trait_desc = get_localized_description(mon_trait, language)

            # Get base stats
            if language == "zh":
                base_stats = f"生命:{mon.base_hp}, 物攻:{mon.base_phy_atk}, 魔攻:{mon.base_mag_atk}, 物防:{mon.base_phy_def}, 魔防:{mon.base_mag_def}, 速度:{mon.base_spd}"
                ref_monster_lines.append(
                    f"- {mon_name}\n"
                    f"  属性: {mon_type_str}\n"
                    f"  特性: {mon_trait_name} — {mon_trait_desc}\n"
                    f"  基础属性: {base_stats}"
                )
            else:
                base_stats = f"HP:{mon.base_hp}, Physical Attack:{mon.base_phy_atk}, Magic Attack:{mon.base_mag_atk}, Physical Defense:{mon.base_phy_def}, Magic Defense:{mon.base_mag_def}, Speed:{mon.base_spd}"
                ref_monster_lines.append(
                    f"- {mon_name}\n"
                    f"  Type: {mon_type_str}\n"
                    f"  Trait: {mon_trait_name} — {mon_trait_desc}\n"
                    f"  Base Stats: {base_stats}"
                )
        referenced_monsters_section = "\n".join(ref_monster_lines)

    # Adjust language in the prompt based on user's language
    if language == "zh":
        prompt = f"""你是一位专业的游戏策略专家，精通洛克王国的对战机制、属性克制和精灵配队。

## 对战机制
说明：以下规则适用于PvP单人模式，是分析队伍和精灵配置的基础：
{BATTLE_MECHANICS_ZH}

## 属性克制表（作为攻击方）
{type_chart}
说明：本表仅描述"攻击方属性X攻击防守方属性Y"时的对阵结果：哪些对阵更有利（克制），哪些对阵不利（效果不佳）。
注意：这里的"效果不佳"不等同于"X被这些属性克制"，请不要反向推断。精灵自身属性只允许用于说明技能的本系加成效果，不允许用于防守克制/抗性分析。

## 游戏术语表
注意：在特性/技能/血脉魔法的描述中出现的术语必须按此表解释。
{glossary}
{f'''
## 引用的技能
注意：以下技能在特性或已选技能的描述中被提及，这里提供其完整信息供参考。
{referenced_moves_section}
''' if referenced_moves_section else ''}{f'''
## 引用的精灵
注意：以下精灵在特性或已选技能的描述中被提及，这里提供其类型信息供参考。
{referenced_monsters_section}
''' if referenced_monsters_section else ''}
---

精灵: {monster_name}
属性: {type_info}
特性: {trait_name} — {trait_desc}

已选技能:
{move_lines_str}

---

指示:
1. 识别哪些技能与特性特别有协同作用。
2. 对于你的建议:
    - 给出**恰好两条建议** (每条最多3-4句话)，**详细解释用户应该如何在不同对局情况下使用所选技能**：
      * 区分哪些技能是通用型的（面对大多数精灵），哪些是特定情况才使用的
      * 说明哪些技能使用后可能获得关键收益（如建立优势、扭转战局），并评估其能耗
      * 给出具体的使用场景建议，包括可能的技能协同、防守/进攻应用，以及如何结合特性和能量管理来发挥最大效果
    - 给出**一条额外的建议** (3-4句话)，**分析技能配置的合理性**：
      * 分析攻击类技能的属性克制覆盖（能够有效克制哪些属性）
      * 分析攻击/防御/状态类技能的配比是否适配特性和对局需求
      * 若技能配置存在重大缺陷（如：没有任何与特性协同的技能、能量配比极度不合理导致无法持续输出、缺少必要的防御手段导致无法应对常见威胁），基于以上分析建议改善方向（但请勿建议具体的技能替换）。若配置合理，则说明其优势。
3. 以以下JSON格式输出 (使用中文回复):
{{
"synergy_moves": [协同技能名称列表],
"recommendation": [建议列表（字符串形式）]
}}
"""
    else:
        prompt = f"""You are an expert game strategist specializing in Roco Kingdom battle mechanics, type matchups, and team composition.

## Battle Mechanics
Note: The following rules apply to PvP solo mode and form the foundation for team and monster analysis.
{BATTLE_MECHANICS_EN}

## Type Effectiveness Table (Attacking Perspective)
{type_chart}
Note: This chart only describes the outcome when the attacking type X hits the defending type Y: which matchups are favorable (effective) and which are unfavorable (weak).
Important: "Unfavorable" here does NOT mean "X is countered by these types." Do not infer the reverse direction. You may mention the monster's own types ONLY for STAB/same-type bonuses, not for defensive weaknesses/resistances.

## Game Terms Glossary
Important: Any terms appearing in trait/move/magic item descriptions must be interpreted using this glossary.
{glossary}
{f'''
## Referenced Moves
Note: The following moves are mentioned in trait or selected move descriptions. Their full details are provided here for reference.
{referenced_moves_section}
''' if referenced_moves_section else ''}{f'''
## Referenced Monsters
Note: The following monsters are mentioned in trait or selected move descriptions. Their type information is provided here for reference.
{referenced_monsters_section}
''' if referenced_monsters_section else ''}
---

Monster: {monster_name}
Type: {type_info}
Trait: {trait_name} — {trait_desc}

Selected moves:
{move_lines_str}

---

Instructions:
1. Identify which moves are especially synergistic with the trait.
2. For your recommendations:
    - Give **exactly two recommendations** (3-4 sentences each) that **explain in detail how to use the selected moves in different battle situations**:
      * Distinguish which moves are versatile (against most monsters) vs situational (for specific scenarios)
      * Identify which moves can provide key benefits after use (e.g., establishing advantage, turning the tide) and assess their energy cost
      * Provide specific usage scenarios including possible move synergies, defensive/offensive applications, and how to maximize effectiveness through trait synergy and energy management
    - Give **one additional recommendation** (3-4 sentences) that **analyzes the moveset's composition**:
      * Analyze the type coverage of attacking moves (which types are effectively countered)
      * Analyze whether the attack/defense/status move ratio fits the trait and battle requirements
      * If the moveset has major flaws (e.g., zero trait-synergy moves, extremely poor energy distribution preventing sustained output, lack of necessary defensive tools against common threats), suggest improvement directions based on the above analysis (but do NOT recommend specific move replacements). If the configuration is sound, highlight its strengths.
3. Output as JSON in the following format:
{{
"synergy_moves": [list of move names],
"recommendation": [list of suggestions as strings]
}}
"""
    return prompt

def build_team_synergy_prompt(user_monsters, monster_db_map, move_db_map, type_db_map, trait_db_map, magic_item, game_terms, referenced_moves, referenced_monsters, language="en", db=None):
    """Build a prompt for team-wide synergy analysis."""
    # Build a summary of each monster in the team
    team_summary_lines = []
    for i, um in enumerate(user_monsters, 1):
        monster = monster_db_map[um.monster_id]
        monster_name = get_localized_name(monster, language)

        # Get types
        main_type = type_db_map[monster.main_type_id]
        main_type_name = get_localized_name(main_type, language)
        type_str = main_type_name
        if monster.sub_type_id:
            sub_type = type_db_map[monster.sub_type_id]
            sub_type_name = get_localized_name(sub_type, language)
            type_str = f"{main_type_name}/{sub_type_name}"

        # Get legacy type and trait
        legacy_type = type_db_map[um.legacy_type_id]
        legacy_type_name = get_localized_name(legacy_type, language)
        trait = trait_db_map[monster.trait_id]
        trait_name = get_localized_name(trait, language)
        trait_desc = get_localized_description(trait, language)

        # Get base stats with localized labels
        if language == "zh":
            base_stats = f"生命:{monster.base_hp}, 物攻:{monster.base_phy_atk}, 魔攻:{monster.base_mag_atk}, 物防:{monster.base_phy_def}, 魔防:{monster.base_mag_def}, 速度:{monster.base_spd}"
        else:
            base_stats = f"HP:{monster.base_hp}, Physical Attack:{monster.base_phy_atk}, Magic Attack:{monster.base_mag_atk}, Physical Defense:{monster.base_phy_def}, Magic Defense:{monster.base_mag_def}, Speed:{monster.base_spd}"

        # Get moves with full details
        moves = [move_db_map[um.move1_id], move_db_map[um.move2_id], move_db_map[um.move3_id], move_db_map[um.move4_id]]
        move_details = []

        # Get personality for dynamic move resolution
        personality = db.query(models.Personality).filter(models.Personality.id == um.personality_id).first() if db else None

        for m in moves:
            move_name = get_localized_name(m, language)
            move_desc = get_localized_description(m, language)

            # Resolve dynamic move properties (for Willpower Impact)
            resolved_props = resolve_dynamic_move_properties(m, um, monster, personality, um.talent, type_db_map)
            resolved_type = resolved_props['type']
            resolved_category = resolved_props['category']

            move_type_name = get_localized_name(resolved_type, language) if resolved_type else "None"
            move_category_str = get_localized_move_category(resolved_category, language)
            energy_cost = getattr(m, 'energy_cost', 'N/A')
            power_str = str(m.power) if m.power is not None else "-"

            if language == "zh":
                move_details.append(f"    - {move_name} (系别：{move_type_name}, 类别：{move_category_str}, 能量消耗:{energy_cost}, 威力:{power_str}): {move_desc}")
            else:
                move_details.append(f"    - {move_name} (Type: {move_type_name}, Category: {move_category_str}, Energy Cost:{energy_cost}, Power:{power_str}): {move_desc}")

        if language == "zh":
            team_summary_lines.append(
                f"{i}. {monster_name} | 属性:{type_str} | 血脉:{legacy_type_name} | 特性:{trait_name} — {trait_desc}\n"
                f"   基础属性: {base_stats}\n"
                f"   技能:\n{chr(10).join(move_details)}"
            )
        else:
            team_summary_lines.append(
                f"{i}. {monster_name} | Type:{type_str} | Legacy Type:{legacy_type_name} | Trait:{trait_name} — {trait_desc}\n"
                f"   Base Stats: {base_stats}\n"
                f"   Moves:\n{chr(10).join(move_details)}"
            )

    team_summary = "\n".join(team_summary_lines)
    magic_item_name = get_localized_name(magic_item, language)
    magic_item_desc = get_localized_description(magic_item, language)

    # Build game terms glossary
    glossary = "\n".join(
        f"- {get_localized_name(gt, language)}: {get_localized_description(gt, language)}" for gt in game_terms
    )

    # Build referenced moves section (moves mentioned in trait/move/magic item descriptions)
    referenced_moves_section = ""
    if referenced_moves:
        ref_move_lines = []
        for m in referenced_moves:
            move_name = get_localized_name(m, language)
            move_desc = get_localized_description(m, language)
            move_type_name = get_localized_name(m.move_type, language) if m.move_type else "None"
            move_category_str = get_localized_move_category(m.move_category, language)
            energy_cost = getattr(m, 'energy_cost', 'N/A')
            power_str = str(m.power) if m.power is not None else "-"

            if language == "zh":
                ref_move_lines.append(f"- {move_name} (系别：{move_type_name}, 类别：{move_category_str}, 能量消耗:{energy_cost}, 威力:{power_str}): {move_desc}")
            else:
                ref_move_lines.append(f"- {move_name} (Type: {move_type_name}, Category: {move_category_str}, Energy Cost:{energy_cost}, Power:{power_str}): {move_desc}")
        referenced_moves_section = "\n".join(ref_move_lines)

    # Build referenced monsters section (monsters mentioned in trait/move/magic item descriptions)
    referenced_monsters_section = ""
    if referenced_monsters:
        ref_monster_lines = []
        for mon in referenced_monsters:
            mon_name = get_localized_name(mon, language)
            mon_main_type = type_db_map[mon.main_type_id]
            mon_type_str = get_localized_name(mon_main_type, language)
            if mon.sub_type_id:
                mon_sub_type = type_db_map[mon.sub_type_id]
                mon_type_str = f"{mon_type_str}/{get_localized_name(mon_sub_type, language)}"

            # Get trait information
            mon_trait = trait_db_map[mon.trait_id]
            mon_trait_name = get_localized_name(mon_trait, language)
            mon_trait_desc = get_localized_description(mon_trait, language)

            # Get base stats
            if language == "zh":
                base_stats = f"生命:{mon.base_hp}, 物攻:{mon.base_phy_atk}, 魔攻:{mon.base_mag_atk}, 物防:{mon.base_phy_def}, 魔防:{mon.base_mag_def}, 速度:{mon.base_spd}"
                ref_monster_lines.append(
                    f"- {mon_name}\n"
                    f"  属性: {mon_type_str}\n"
                    f"  特性: {mon_trait_name} — {mon_trait_desc}\n"
                    f"  基础属性: {base_stats}"
                )
            else:
                base_stats = f"HP:{mon.base_hp}, Physical Attack:{mon.base_phy_atk}, Magic Attack:{mon.base_mag_atk}, Physical Defense:{mon.base_phy_def}, Magic Defense:{mon.base_mag_def}, Speed:{mon.base_spd}"
                ref_monster_lines.append(
                    f"- {mon_name}\n"
                    f"  Type: {mon_type_str}\n"
                    f"  Trait: {mon_trait_name} — {mon_trait_desc}\n"
                    f"  Base Stats: {base_stats}"
                )
        referenced_monsters_section = "\n".join(ref_monster_lines)

    # Build Evolution Power leader forms section
    # If Evolution Power is selected, show the Leader form data for monsters with Leader legacy type
    leader_forms_section = ""
    if db is not None and hasattr(magic_item, 'effect_code') and magic_item.effect_code == models.MagicEffectCode.EVOLUTION_POWER:
        leader_form_lines = []
        for um in user_monsters:
            # Check if this monster has Leader legacy type
            legacy_type = type_db_map[um.legacy_type_id]
            legacy_type_name = get_localized_name(legacy_type, language)

            if legacy_type_name in ["Leader", "首领"]:
                # Get the base monster
                base_monster = monster_db_map[um.monster_id]

                # Query for the leader form of this monster (same species, is_leader_form=True)
                leader_form = db.query(models.Monster).filter(
                    models.Monster.species_id == base_monster.species_id,
                    models.Monster.is_leader_form == True
                ).first()

                if leader_form:
                    # Get leader form details
                    leader_name = get_localized_name(leader_form, language)
                    base_monster_name = get_localized_name(base_monster, language)

                    # Get leader form types
                    leader_main_type = type_db_map[leader_form.main_type_id]
                    leader_type_str = get_localized_name(leader_main_type, language)
                    if leader_form.sub_type_id:
                        leader_sub_type = type_db_map[leader_form.sub_type_id]
                        leader_type_str = f"{leader_type_str}/{get_localized_name(leader_sub_type, language)}"

                    # Get leader form trait (load if not already in map)
                    if leader_form.trait_id not in trait_db_map:
                        leader_trait_obj = db.query(models.Trait).filter(models.Trait.id == leader_form.trait_id).first()
                        if leader_trait_obj:
                            trait_db_map[leader_form.trait_id] = leader_trait_obj

                    leader_trait = trait_db_map.get(leader_form.trait_id)
                    if not leader_trait:
                        # Skip this monster if trait cannot be loaded
                        continue

                    leader_trait_name = get_localized_name(leader_trait, language)
                    leader_trait_desc = get_localized_description(leader_trait, language)

                    # Get leader form base stats
                    if language == "zh":
                        leader_stats = f"生命:{leader_form.base_hp}, 物攻:{leader_form.base_phy_atk}, 魔攻:{leader_form.base_mag_atk}, 物防:{leader_form.base_phy_def}, 魔防:{leader_form.base_mag_def}, 速度:{leader_form.base_spd}"
                        leader_form_lines.append(
                            f"- {base_monster_name} → 进化为 {leader_name}\n"
                            f"  属性: {leader_type_str}\n"
                            f"  特性: {leader_trait_name} — {leader_trait_desc}\n"
                            f"  基础属性: {leader_stats}"
                        )
                    else:
                        leader_stats = f"HP:{leader_form.base_hp}, Physical Attack:{leader_form.base_phy_atk}, Magic Attack:{leader_form.base_mag_atk}, Physical Defense:{leader_form.base_phy_def}, Magic Defense:{leader_form.base_mag_def}, Speed:{leader_form.base_spd}"
                        leader_form_lines.append(
                            f"- {base_monster_name} → Evolves to {leader_name}\n"
                            f"  Type: {leader_type_str}\n"
                            f"  Trait: {leader_trait_name} — {leader_trait_desc}\n"
                            f"  Base Stats: {leader_stats}"
                        )

        if leader_form_lines:
            leader_forms_section = "\n".join(leader_form_lines)

    # Build Willpower Enhancement section
    # If Willpower Enhancement is selected, show which monsters can use it and what type/category they get
    willpower_enhancement_section = ""
    if db is not None and hasattr(magic_item, 'effect_code') and magic_item.effect_code == models.MagicEffectCode.ENHANCE_SPELL:
        willpower_lines = []
        eligible_count = 0

        # Find the Leader type ID
        leader_type_id = next((t.id for t in type_db_map.values() if t.name == "Leader"), None)

        for um in user_monsters:
            # Check if this monster can use Willpower Enhancement (not Leader legacy type)
            legacy_type = type_db_map[um.legacy_type_id]
            legacy_type_name = get_localized_name(legacy_type, language)

            if um.legacy_type_id != leader_type_id:
                eligible_count += 1
                base_monster = monster_db_map[um.monster_id]
                monster_name = get_localized_name(base_monster, language)

                # Get personality for stat comparison
                personality = db.query(models.Personality).filter(models.Personality.id == um.personality_id).first()

                if personality:
                    # Compute effective stats to determine if Willpower Impact will be Physical or Magical
                    effective_stats = compute_effective_stats(base_monster, personality, um.talent)
                    is_physical = effective_stats.phy_atk > effective_stats.mag_atk

                    if language == "zh":
                        attack_type = "物理攻击" if is_physical else "魔法攻击"
                        willpower_lines.append(
                            f"- {monster_name}: 愿力冲击将成为 {legacy_type_name} 系别的 {attack_type} 技能"
                        )
                    else:
                        attack_type = "Physical Attack" if is_physical else "Magic Attack"
                        willpower_lines.append(
                            f"- {monster_name}: Willpower Impact will become a {legacy_type_name}-type {attack_type} move"
                        )

        if willpower_lines:
            if language == "zh":
                willpower_enhancement_section = (
                    f"注意：队伍选择了「愿力强化」血脉魔法。此魔法可以被队内 {eligible_count} 个精灵使用（首领血脉除外）。\n"
                    f"该魔法有3回合冷却时间，但在单场战斗中可以多次用于不同精灵。\n\n"
                    f"使用后，该精灵的第1个技能在本回合被替换为「愿力冲击」：\n"
                    f"- 愿力冲击 (系别：根据使用精灵的血脉属性动态变化, 类别：物攻/魔攻, 能量消耗:2, 威力:80): "
                    f"造成物理/魔法伤害（取决于使用精灵的物攻和魔攻哪个更高），应对成功时本次威力提高150%，应对状态。\n\n"
                    f"这是该血脉魔法的核心战术价值：通过血脉属性获得额外的攻击覆盖面和应对覆盖面。以下是各精灵使用该魔法时的愿力冲击效果：\n"
                    + "\n".join(willpower_lines)
                )
            else:
                willpower_enhancement_section = (
                    f"Note: The team has selected \"Willpower Enhancement\" magic item. This item can be used by {eligible_count} monsters in the team (except those with Leader legacy type). \n"
                    f"The item has a 3-turn cooldown but can be used multiple times in a single battle on different monsters.\n\n"
                    f"When used, the monster's 1st move is replaced with \"Willpower Impact\" for that turn:\n"
                    f"- Willpower Impact (Type: Dynamically matches user's legacy type, Category: Physical/Magic Attack, Energy Cost:2, Power:80): "
                    f"Deals physical or magic damage (based on user's higher attack stat). If this move counters successfully, power +150%. Counter Status.\n\n"
                    f"This is the core tactical value of this magic item: gaining additional offensive coverage and counter coverage through legacy types. Here's what Willpower Impact will be for each eligible monster:\n"
                    + "\n".join(willpower_lines)
                )

    # Build complete type effectiveness table
    type_chart_lines = []
    all_types = sorted(type_db_map.values(), key=lambda t: get_localized_name(t, language))
    for t in all_types:
        type_name = get_localized_name(t, language)
        if type_name in ["Leader", "首领"]:
            continue

        effective = []
        weak = []
        if hasattr(t, 'effective_against') and t.effective_against:
            effective = sorted([get_localized_name(target, language) for target in t.effective_against])
        if hasattr(t, 'weak_against') and t.weak_against:
            weak = sorted([get_localized_name(target, language) for target in t.weak_against])

        if language == "zh":
            eff_str = ', '.join(effective) if effective else '无'
            weak_str = ', '.join(weak) if weak else '无'
            type_chart_lines.append(f"  {type_name} → 克制: {eff_str} | 效果不佳: {weak_str}")
        else:
            eff_str = ', '.join(effective) if effective else 'None'
            weak_str = ', '.join(weak) if weak else 'None'
            type_chart_lines.append(f"  {type_name} → Effective Against: {eff_str} | Weak Against: {weak_str}")

    type_chart = "\n".join(type_chart_lines)

    if language == "zh":
        prompt = f"""你是一位专业的游戏策略专家，精通洛克王国的对战机制、属性克制和精灵配队。

## 对战机制
说明：以下规则适用于PvP单人模式，是分析队伍和精灵配置的基础：
{BATTLE_MECHANICS_ZH}

## 属性克制表（作为攻击方）
{type_chart}
说明：本表仅描述"攻击方属性X攻击防守方属性Y"时的对阵结果：哪些对阵更有利（克制），哪些对阵不利（效果不佳）。
注意：这里的"效果不佳"不等同于"X被这些属性克制"，请不要反向推断。精灵自身属性只允许用于说明技能的本系加成效果，不允许用于防守克制/抗性分析。

## 游戏术语表
注意：在特性/技能/血脉魔法的描述中出现的术语必须按此表解释。
{glossary}
{f'''
## 引用的技能
注意：以下技能在特性或已选技能的描述中被提及，这里提供其完整信息供参考。
{referenced_moves_section}
''' if referenced_moves_section else ''}{f'''
## 引用的精灵
注意：以下精灵在特性或已选技能的描述中被提及，这里提供其信息供参考。
{referenced_monsters_section}
''' if referenced_monsters_section else ''}
---

队伍组成:
{team_summary}

血脉魔法: {magic_item_name} — {magic_item_desc}
{f'''

## 进化之力效果
注意：队伍选择了"进化之力"血脉魔法。以下精灵仅在玩家主动对其使用该血脉魔法的回合内进化为首领形态（进化时机由玩家选择）。一旦进化，该精灵将在本场战斗的剩余时间内保持首领形态，除非被特定技能或效果强制退化。分析时请考虑进化后的属性、特性和战术定位的变化，以及何时使用该魔法以触发进化的战术价值。
{leader_forms_section}
''' if leader_forms_section else ''}{f'''

## 愿力强化效果
{willpower_enhancement_section}
''' if willpower_enhancement_section else ''}

---

## 队伍整体协同作用分析
> **硬性要求**：所有结论必须**结合队内具体精灵与其「特性 / 技能类别（攻击/防御/状态）/ 能量消耗 / 应对标签 / 迅捷 / 血脉魔法」**来论证，避免泛泛而谈。

### 1) 队伍定位与战术体系
* **战术类型判定（写 2–3 句话）**
判定队伍属于养成/控制/消耗/平衡/反制体系中的哪一种或两种混合，并用队内配置证明：至少点出**核心输出结构（物攻/魔攻/混合）**、**防守与控场资源（防御/状态）**、以及**能量曲线（稳定低能耗循环 vs 依赖"聚能回合"来维持技能释放/关键回合能量）**各自由哪些精灵与技能承担。
* **体系核心与闭环链条（写 3–4 句话）**
指定 **2–4 只"体系核心/关键枢纽"**，逐一说明它们分别负责什么（增益/减益/控制/能量压制/应对触发/收割），并把它们串成一个闭环：
"谁负责铺垫 → 谁负责承伤/控场 → 谁负责触发应对或迅捷 → 谁负责终结"。必须明确引用：相关特性效果、技能类别与能耗、应对标签或迅捷触发条件。
* **节奏拆解（开局→中期→终局）（写 3–4 句话）**
给出清晰的战斗节奏路线：开局如何建立优势（例如先手压制/控场/压低对手能量），中期如何滚雪球（例如叠层、持续压迫对手能量或逼换），终局如何收割（明确由谁收割、靠什么能量/应对/迅捷窗口）。同时指出队伍是否**依赖速度优势**或**依赖应对系统**启动，以及如果启动失败会出现什么代价。

### 2) 行动优先级与应对策略
* **先手/后手角色划分与出手排序（写 3–4 句话）**
基于速度与技能定位，把队内精灵分成：先手压制位、后手反制位、站场/承伤位、机会收割位。说明你的建议出手顺序（谁更适合先动/后动），并用证据支撑：例如技能类别与能耗是否允许频繁出手、是否依赖聚能、是否依赖触发类特性/迅捷。
* **应对三角（防御↔攻击↔状态）的执行人（写 3–4 句话）**
说明队伍如何利用应对三角做反制：
  * 哪些精灵/技能更适合用"防御"应对对手攻击
  * 哪些更适合用"攻击"压制对手状态
  * 哪些更适合用"状态"反制对手防御
必须点名队内**最适合执行应对的精灵**及其依据（应对标签、技能类别、能耗、特性触发条件），并指出可能的失败点（例如能量断档/怕被对手同类反制）。
* **能量经济评估与资源分配（写 3–4 句话）**
评价队伍能量是否健康：是否存在稳定低能耗循环、回复能量/降耗机制、或逼迫对手聚能的手段（例如持续压能/提高对手技能能耗）。若队伍自身经常需要聚能来维持关键技能释放，则必须明确：哪只精灵在聚能时最不容易被击穿/被逼换，以及聚能带来的收益（能量回补后能立刻形成输出/控场/应对优势）与代价（丢回合导致掉节奏、被对手换入压制、或被反向应对）。

### 3) 轮换与进场策略
* **安全换入点/防守支点/节奏转换点（写 3–4 句话）**
找出队内能稳定换入的精灵（能吃伤害、能用防御/状态稳局面、或能逼退对手），并解释每个"换入点"成立的原因：特性带来的抗压/免疫/回血/脱离/进场收益？技能类别与低能耗是否允许立刻稳住？是否具备应对标签可反制对手的常见出手？
* **主动换人的触发场景（写 2–3 句话）**
列出至少 2 种应主动换人的局面：例如当前精灵能量枯竭、关键核心需要保护、需要切入制造关键回合（应对窗口/控场窗口/收割窗口）。每个场景都要说明：换到谁、为什么换他（能耗/应对/速度/特性/技能类别）。
* **迅捷相关的换入收益与风险（写 2–3 句话）**
如果队内存在带"迅捷"效果的技能：说明如何通过主动换入触发迅捷建立优势——谁负责触发、触发后的收益（先手权/抢节奏/应对优先级变化/能量收益）、以及风险（换入吃伤害、被对手预判克制、迅捷窗口被状态/防御应对打断等）。
如果队内不存在迅捷技能：简要说明这意味着队伍缺少迅捷战术选项，并评估这对队伍节奏控制的影响（例如：是否依赖其他方式抢先手、或是否通过应对系统弥补）。

### 4) 血脉魔法的最优化使用
* **最适配对象与轮转思路（写 3–4 句话）**
若血脉魔法一场战斗中只能使用一次：指出最值得给的 1 只精灵，并说明原因（与其特性/技能类别/能耗曲线/应对标签/迅捷或收割能力的契合点）。
若可多次使用或有冷却：给出适配的 2–3 只精灵与轮转逻辑（什么局面给谁、为何能提高全队胜率/稳定性）。
* **具体使用时机（写 2–3 句话）**
提供 1–2 个明确的使用时机：例如配合某关键技能回合、弥补能量断档、丰富应对种类、或提升精灵整体强度。必须讲清楚"使用前提"和"预期收益"。
* **匹配度评估（写 2–3 句话）**
若血脉魔法可以被队内精灵正常使用：用一句话确认匹配度良好，再用1-2句话简述该魔法与队伍战术的契合点或潜在协同。
若血脉魔法无法被任何队伍成员使用：用一句话解释原因，再用两句话给出调整思路（如何修改队内配置以符合使用标准，或根据队伍优势建议魔法替换方向，仅描述功能方向不提供具体名称）。

### 5) 整体战术建议与结构性弱点
* **胜利条件与达成路径（写 3–4 句话）**
用 1–2 条总结队伍主要胜利条件（例如"通过能量压制+应对链条滚雪球后收割"或"靠速度与迅捷抢关键回合打穿"），并写清楚达成路径需要的前置条件：至少包含能量状态、关键精灵存活/进场条件、应对链条是否成立。
* **最容易被针对的节奏点（写 3–4 句话）**
指出队伍最脆弱的 1–2 个结构性问题：如能量断档、缺乏稳定防守回合、过度依赖某核心、或对某类状态/防御体系缺少反制。每个弱点都要落到具体证据（哪个精灵、哪类技能、哪个能耗节点、哪个应对标签缺口）。
* **规避与调整建议（写 3–4 句话）**
从以下方向里选择最关键的 1–2 条给出"可执行"的建议：出手优先级调整 / 应对策略调整 / 轮换触发点设计 / 能量管理方案 / 技能或精灵替换建议。必须明确：改动点是什么、解决哪个弱点、带来的副作用是什么。

以以下JSON格式输出（用中文回复）：
{{
"team_archetype": {{
  "tactical_type": "战术类型判定的内容",
  "core_loop": "体系核心与闭环链条的内容",
  "battle_rhythm": "节奏拆解的内容"
}},
"action_priority": {{
  "role_assignment": "先手/后手角色划分与出手排序的内容",
  "counter_triangle": "应对三角的执行人的内容",
  "energy_economy": "能量经济评估与资源分配的内容"
}},
"switching_strategy": {{
  "pivot_points": "安全换入点/防守支点/节奏转换点的内容",
  "active_switch_scenarios": "主动换人的触发场景的内容",
  "quick_entry_synergy": "迅捷相关的换入收益与风险的内容"
}},
"magic_item_usage": {{
  "best_targets": "最适配对象与轮转思路的内容",
  "timing": "具体使用时机的内容",
  "mismatch_analysis": "匹配度评估的内容"
}},
"overall_strategy": {{
  "win_conditions": "胜利条件与达成路径的内容",
  "vulnerable_points": "最容易被针对的节奏点的内容",
  "adjustments": "规避与调整建议的内容"
}}
}}
"""
    else:
        prompt = f"""You are an expert game strategist specializing in Roco Kingdom battle mechanics, type matchups, and team composition.

## Battle Mechanics
Note: The following rules apply to PvP solo mode and form the foundation for team and monster analysis.
{BATTLE_MECHANICS_EN}

## Type Effectiveness Table (Attacking Perspective)
{type_chart}
Note: This chart only describes the outcome when the attacking type X hits the defending type Y: which matchups are favorable (effective) and which are unfavorable (weak).
Important: "Unfavorable" here does NOT mean "X is countered by these types." Do not infer the reverse direction. You may mention the monster's own types ONLY for STAB/same-type bonuses, not for defensive weaknesses/resistances.

## Game Terms Glossary
Important: Any terms appearing in trait/move/magic item descriptions must be interpreted using this glossary.
{glossary}
{f'''
## Referenced Moves
Note: The following moves are mentioned in trait or selected move descriptions. Their full details are provided here for reference.
{referenced_moves_section}
''' if referenced_moves_section else ''}{f'''
## Referenced Monsters
Note: The following monsters are mentioned in trait or selected move descriptions. Their information is provided here for reference.
{referenced_monsters_section}
''' if referenced_monsters_section else ''}
---

Team Composition:
{team_summary}

Magic Item: {magic_item_name} — {magic_item_desc}
{f'''

## Evolution Power Effect
Note: The team has selected the "Evolution Power" magic item. The following monsters will evolve into their Leader forms only when the player actively uses this magic item on them during a specific turn (timing chosen by the player). Once evolved, the monster will remain in its Leader form for the rest of the battle, unless forcibly devolved by certain moves or effects. In your analysis, consider the changes in stats, traits, and tactical positioning after evolution, as well as the strategic value of when to use this magic item to trigger the evolution.
{leader_forms_section}
''' if leader_forms_section else ''}{f'''

## Willpower Enhancement Effect
{willpower_enhancement_section}
''' if willpower_enhancement_section else ''}

---

## Team Synergy Analysis
> **Critical Requirement**: All conclusions must be **grounded in specific monsters and their traits/move categories (Attack/Defense/Status)/energy costs/counter tags/Quick Entry/Magic Item**, avoiding generic statements.

### 1) Team Archetype & Tactical System
* **Tactical Type Identification (2-3 sentences)**
Determine whether the team follows a setup/control/attrition/balanced/reactive archetype (or a hybrid), and justify using the team's configuration: at minimum, identify the **core damage structure (Physical/Magical/Hybrid)**, **defensive and control resources (Defense/Status)**, and **energy curve (stable low-cost loops vs reliance on "Focus turns" to maintain move usage/critical turns)**, specifying which monsters and moves handle each role.
* **Core Members & Closed Loop (3-4 sentences)**
Designate **2-4 "core members/key pivots"**, explain what each handles (buffs/debuffs/control/energy pressure/counter triggers/sweeping), and connect them into a closed loop:
"Who sets up → Who tanks/controls → Who triggers counters or Quick Entry → Who finishes". Must explicitly reference: relevant trait effects, move categories and costs, counter tags, or Quick Entry trigger conditions.
* **Battle Rhythm Breakdown (Early → Mid → Late) (3-4 sentences)**
Provide a clear battle rhythm roadmap: how to establish early advantage (e.g., first-strike pressure/control/draining opponent energy), how to snowball mid-game (e.g., stacking layers, continuous energy pressure or forcing switches), how to close out late (specify who finishes, via what energy/counter/Quick Entry window). Also indicate whether the team **relies on speed advantage** or **relies on counter system** to initiate, and what happens if initiation fails.

### 2) Action Priority & Counter Strategy
* **First-Strike/Reactive Role Assignment & Turn Order (3-4 sentences)**
Based on speed and move positioning, categorize team monsters into: first-strike pressure, reactive counter, tank/absorber, opportunistic sweeper. Explain your recommended turn order (who should move first/last), with evidence: e.g., whether move category and cost allow frequent action, whether they depend on Focus, whether they depend on trigger-based traits/Quick Entry.
* **Counter Triangle (Defense↔Attack↔Status) Executors (3-4 sentences)**
Explain how the team leverages the counter triangle for reactive play:
  * Which monsters/moves best use "Defense" to counter opponent Attacks
  * Which best use "Attack" to pressure opponent Status
  * Which best use "Status" to counter opponent Defense
Must name the **best counter executors** in the team with justification (counter tags, move categories, costs, trait trigger conditions), and point out potential failure modes (e.g., energy drought/vulnerable to opponent's same-type counter).
* **Energy Economy Assessment & Resource Allocation (3-4 sentences)**
Evaluate whether the team's energy is healthy: does it have stable low-cost loops, energy refund/cost reduction mechanisms, or ways to force opponent Focus (e.g., continuous pressure/increasing opponent move costs). If the team itself often needs Focus to maintain key move usage, must specify: which monster is least likely to be broken/forced out during Focus, and Focus benefits (immediate damage/control/counter advantage after energy recovery) vs costs (losing tempo, being pressured by opponent switches, or being reverse-countered).

### 3) Switching & Entry Strategy
* **Safe Switch-Ins/Defensive Pivots/Tempo Shifters (3-4 sentences)**
Identify monsters that can safely switch in (can take hits, stabilize with Defense/Status, or force opponent switches), and explain why each "switch-in point" works: does the trait provide durability/immunity/healing/escape/entry benefits? Do move categories and low costs allow immediate stabilization? Do they have counter tags to react to common opponent actions?
* **Active Switch Triggers (2-3 sentences)**
List at least 2 scenarios requiring active switches: e.g., current monster's energy depleted, protecting key sweepers, bringing in a counter for a critical turn (counter window/control window/sweep window). For each scenario, specify: switch to whom, why (cost/counter/speed/trait/move category).
* **Quick Entry Synergy, Benefits & Risks (2-3 sentences)**
If Quick Entry moves exist: explain how to leverage active switch-ins to trigger Quick Entry for advantage—who triggers, post-trigger benefits (priority/tempo steal/counter priority shift/energy gain), and risks (switch-in takes damage, opponent predicts and counters, Quick Entry window interrupted by Status/Defense counters, etc.).
If no Quick Entry moves exist: briefly note that the team lacks Quick Entry tactical options and assess the impact on tempo control (e.g., whether relying on other methods for priority, or compensating via the counter system).

### 4) Magic Item Optimization
* **Best Targets & Rotation Logic (3-4 sentences)**
If magic item is one-time use: identify the 1 monster most worth using it on, with reasoning (synergy with trait/move category/energy curve/counter tags/Quick Entry or sweep potential).
If it is multi-use or has cooldown: provide 2-3 best-fit monsters and rotation logic (what situation for whom, why it improves team win rate/stability).
* **Specific Usage Timing (2-3 sentences)**
Provide 1-2 concrete usage timings: e.g., combo with key move turn, covering energy gaps, enriching counter variety, or boosting monster overall power. Must clarify "prerequisites" and "expected benefits".
* **Compatibility Assessment (2-3 sentences)**
If the magic item can be used by team monsters: confirm good compatibility in one sentence, then briefly describe synergies between the item and team tactics in 1-2 sentences.
If the magic item cannot be used by any team member: explain why in one sentence, then provide adjustment ideas in two sentences (how to modify team configuration to meet usage requirements, or suggest magic item replacement direction based on team strengths—functional direction only, no specific names).

### 5) Overall Strategy & Structural Weaknesses
* **Win Conditions & Achievement Paths (3-4 sentences)**
Summarize the team's 1-2 primary win conditions (e.g., "snowball via energy pressure + counter chains then sweep" or "steal critical turns via speed + Quick Entry to break through"), and clarify the prerequisites for achieving them: at minimum, include energy state, key monster survival/entry conditions, whether counter chains hold.
* **Most Exploitable Tempo Vulnerabilities (3-4 sentences)**
Identify the team's 1-2 most fragile structural issues: e.g., energy drought, lack of stable defensive turns, over-reliance on certain cores, or lack of counter-play against certain Status/Defense archetypes. Each weakness must be backed by concrete evidence (which monster, which move type, which energy node, which counter tag gap).
* **Mitigation & Adjustment Recommendations (3-4 sentences)**
From the following directions, select the most critical 1-2 for "actionable" recommendations: action priority adjustments / counter strategy adjustments / switching trigger design / energy management plans / move or monster swap suggestions. Must specify: what to change, which weakness it addresses, what side effects it brings.

Output as JSON in the following format:
{{
"team_archetype": {{
  "tactical_type": "Content for tactical type identification",
  "core_loop": "Content for core members and closed loop",
  "battle_rhythm": "Content for battle rhythm breakdown"
}},
"action_priority": {{
  "role_assignment": "Content for role assignment and turn order",
  "counter_triangle": "Content for counter triangle executors",
  "energy_economy": "Content for energy economy assessment"
}},
"switching_strategy": {{
  "pivot_points": "Content for safe switch-ins/pivots/tempo shifters",
  "active_switch_scenarios": "Content for active switch triggers",
  "quick_entry_synergy": "Content for Quick Entry synergy, benefits & risks"
}},
"magic_item_usage": {{
  "best_targets": "Content for best targets and rotation logic",
  "timing": "Content for specific usage timing",
  "mismatch_analysis": "Content for compatibility assessment"
}},
"overall_strategy": {{
  "win_conditions": "Content for win conditions and achievement paths",
  "vulnerable_points": "Content for most exploitable vulnerabilities",
  "adjustments": "Content for mitigation and adjustment recommendations"
}}
}}
"""
    return prompt

# Compute team-level analysis
def compute_type_coverage(user_monsters, move_db_map, monster_db_map, type_db_map, personality_db_map=None, magic_item=None):
    """
    Compute offensive type coverage for a team.

    If magic_item is Willpower Enhancement (愿力强化), returns both:
    - Base coverage (original moves only)
    - Enhanced coverage (with legacy types added as Willpower Impact)
    """
    IGNORED_TYPE_NAMES = {"Leader"}
    ignored_type_ids = {t.id for t in type_db_map.values() if t.name in IGNORED_TYPE_NAMES}
    all_type_ids = set(type_db_map.keys()) - ignored_type_ids

    # Helper function to compute coverage for a given set of attack types
    def compute_coverage_levels(attack_type_ids_set):
        if not attack_type_ids_set:
            # No attack moves
            return {
                "super_effective_types": [],
                "neutral_types": [],
                "resisted_types": sorted(all_type_ids),
            }

        super_effective_types = []
        neutral_types = []
        resisted_types = []

        for def_type_id in all_type_ids:
            def_type = type_db_map[def_type_id]

            # Check if any attack type is super-effective
            has_super_effective = any(
                def_type in type_db_map[atk_id].effective_against
                for atk_id in attack_type_ids_set
            )

            if has_super_effective:
                super_effective_types.append(def_type_id)
                continue

            # Check if any attack type is at least neutral (not resisted)
            has_non_resisted_option = any(
                def_type not in type_db_map[atk_id].weak_against
                for atk_id in attack_type_ids_set
            )

            if has_non_resisted_option:
                neutral_types.append(def_type_id)
            else:
                resisted_types.append(def_type_id)

        return {
            "super_effective_types": sorted(super_effective_types),
            "neutral_types": sorted(neutral_types),
            "resisted_types": sorted(resisted_types),
        }

    # Gather all ATTACK move types for offense (exclude STATUS/DEFENSE)
    attack_type_ids = set()
    for um in user_monsters:
        base_monster = monster_db_map[um.monster_id]
        personality = personality_db_map.get(um.personality_id) if personality_db_map else None

        for move_id in [um.move1_id, um.move2_id, um.move3_id, um.move4_id]:
            move = move_db_map[move_id]

            # Only count ATTACK category moves (PHY_ATTACK or MAG_ATTACK)
            if move.move_category not in [models.MoveCategory.PHY_ATTACK, models.MoveCategory.MAG_ATTACK]:
                continue  # Skip STATUS/DEFENSE moves

            # Resolve dynamic move properties if needed
            if personality and move.name == "Willpower Impact":
                resolved_props = resolve_dynamic_move_properties(move, um, base_monster, personality, um.talent, type_db_map)
                if resolved_props['type']:
                    attack_type_ids.add(resolved_props['type'].id)
            elif move.move_type_id:
                attack_type_ids.add(move.move_type_id)

    # Compute base coverage (original moves only)
    base_coverage = compute_coverage_levels(attack_type_ids)

    # Check if Willpower Enhancement (愿力强化) is active
    willpower_enhancement_active = (
        magic_item and
        getattr(magic_item, "effect_code", None) == models.MagicEffectCode.ENHANCE_SPELL
    )

    # Compute enhanced coverage if Willpower Enhancement is active
    enhanced_coverage = None
    if willpower_enhancement_active:
        leader_type_id = next((t.id for t in type_db_map.values() if t.name == "Leader"), None)
        enhanced_attack_types = attack_type_ids.copy()

        # Add legacy types as additional attack types (simulating Willpower Impact)
        for um in user_monsters:
            legacy_type_id = um.legacy_type_id
            # Add if legacy type exists and is not Leader (Willpower Enhancement doesn't work on Leader)
            if legacy_type_id and legacy_type_id != leader_type_id:
                enhanced_attack_types.add(legacy_type_id)

        enhanced_coverage = compute_coverage_levels(enhanced_attack_types)

    # Defensive weakness, build weakness count per type across team
    type_weak_count = Counter()
    all_types = list(type_db_map.values())
    for um in user_monsters:
        base_monster = monster_db_map[um.monster_id]
        main_type = type_db_map[base_monster.main_type_id]
        sub_type = type_db_map[base_monster.sub_type_id] if base_monster.sub_type_id else None

        for attacking_type in all_types:
            weak_main = attacking_type in main_type.vulnerable_to
            weak_sub = sub_type and attacking_type in sub_type.vulnerable_to

            resist_main = attacking_type in main_type.resistant_to
            resist_sub = sub_type and attacking_type in sub_type.resistant_to

            # Per-monster weakness logic
            is_weak = False
            if weak_main and weak_sub:
                is_weak = True
            elif (weak_main and not resist_sub and not weak_sub) or (weak_sub and not resist_main and not weak_main):
                is_weak = True

            if is_weak:
                type_weak_count[attacking_type.id] += 1

    # Only include types that appear >= 3 times
    team_weak_to = [type_id for type_id, count in type_weak_count.items() if count >= 3]

    # Build result with base coverage
    result = {
        "super_effective_types": base_coverage["super_effective_types"],
        "neutral_types": base_coverage["neutral_types"],
        "resisted_types": base_coverage["resisted_types"],
        "team_weak_to": sorted(team_weak_to),
        # Backward compatibility (deprecated)
        "effective_against_types": base_coverage["super_effective_types"],
        "weak_against_types": base_coverage["resisted_types"],
    }

    # Add enhanced coverage if Willpower Enhancement is active
    if enhanced_coverage:
        result["enhanced_coverage"] = {
            "super_effective_types": enhanced_coverage["super_effective_types"],
            "neutral_types": enhanced_coverage["neutral_types"],
            "resisted_types": enhanced_coverage["resisted_types"],
        }

    return result
    
def compute_magic_item_eval(magic_item, user_monster_outs, type_db_map):
    valid_targets = []

    # Dynamic type IDs by name
    TYPE_NAME_TO_ID = {t.name.lower(): t.id for t in type_db_map.values()}
    GRASS_TYPE_ID = TYPE_NAME_TO_ID.get("grass")
    FIRE_TYPE_ID = TYPE_NAME_TO_ID.get("fire")
    WATER_TYPE_ID = TYPE_NAME_TO_ID.get("water")
    LEADER_TYPE_ID = TYPE_NAME_TO_ID.get("leader")

    effect_code = getattr(magic_item, "effect_code", None)

    for user_monster in user_monster_outs:
        m = user_monster.monster  # MonsterLiteOut
        legacy_type_id = getattr(user_monster.legacy_type, "id", None)
        main_type_id = getattr(m.main_type, "id", None)
        sub_type_id = getattr(m.sub_type, "id", None)

        # Willpower Enhancement: any monster except Leader legacy type
        if effect_code == models.MagicEffectCode.ENHANCE_SPELL:
            if legacy_type_id != LEADER_TYPE_ID:
                valid_targets.append(user_monster.id)

        # Sun Healing: grass main/sub/legacy
        elif effect_code == models.MagicEffectCode.SUN_HEALING:
            if ((main_type_id == GRASS_TYPE_ID) or
                (sub_type_id == GRASS_TYPE_ID) or
                (legacy_type_id == GRASS_TYPE_ID)):
                valid_targets.append(user_monster.id)

        # Flare Burst: fire main/sub/legacy
        elif effect_code == models.MagicEffectCode.FLARE_BURST:
            if ((main_type_id == FIRE_TYPE_ID) or
                (sub_type_id == FIRE_TYPE_ID) or
                (legacy_type_id == FIRE_TYPE_ID)):
                valid_targets.append(user_monster.id)

        # Flow Spell: water main/sub/legacy
        elif effect_code == models.MagicEffectCode.FLOW_SPELL:
            if ((main_type_id == WATER_TYPE_ID) or
                (sub_type_id == WATER_TYPE_ID) or
                (legacy_type_id == WATER_TYPE_ID)):
                valid_targets.append(user_monster.id)

        # Evolution Power: only if leader_potential and legacy type is Leader
        elif effect_code == models.MagicEffectCode.EVOLUTION_POWER:
            if getattr(m, "leader_potential", False) and (legacy_type_id == LEADER_TYPE_ID):
                valid_targets.append(user_monster.id)

    # More logic can be added here for other analysis aspects
    return {
        "chosen_item": magic_item,
        "valid_targets": valid_targets,
        "best_target_monster_id": None,
        "reasoning": None,
    }

def generate_recommendations(per_monster_analysis, type_coverage, magic_item_eval, move_db_map, type_db_map, language="en"):
    recs: List[schemas.RecItem] = []

    def add(category, severity, message, *, type_ids=None, monster_ids=None, move_ids=None):
        recs.append(schemas.RecItem(
            category=category,
            severity=severity,
            message=message,
            type_ids=type_ids or [],
            monster_ids=monster_ids or [],
            move_ids=move_ids or []
        ))

    # 1) Type coverage – offense (resisted types only)
    if type_coverage["resisted_types"]:
        names = [get_localized_name(type_db_map[t], language) for t in type_coverage["resisted_types"]]
        if language == "zh":
            add("coverage", "danger",
                f"你的攻击技能被以下属性完全抵抗：{', '.join(names)}。建议增加其他属性的攻击技能以提升覆盖面。",
                type_ids=type_coverage["resisted_types"])
        else:
            add("coverage", "danger",
                f"Your team's attacks are resisted by: {', '.join(names)}. Add different attack types for better coverage.",
                type_ids=type_coverage["resisted_types"])

    # 2) Team defensive weaknesses
    if type_coverage["team_weak_to"]:
        names = [get_localized_name(type_db_map[t], language) for t in type_coverage["team_weak_to"]]
        if language == "zh":
            add("weakness", "danger",
                f"你的队伍特别容易受到这些属性的攻击：{', '.join(names)}。建议考虑防守选项或抗性。",
                type_ids=type_coverage["team_weak_to"])
        else:
            add("weakness", "danger",
                f"Your team is especially vulnerable to: {', '.join(names)}. Consider defensive options or resistances.",
                type_ids=type_coverage["team_weak_to"])

    # 3) Magic item usage
    vt = magic_item_eval.valid_targets
    if not vt:
        if language == "zh":
            add("magic_item", "danger", "当前队伍中没有精灵可以使用所选择的血脉魔法！")
        else:
            add("magic_item", "danger", "Your selected magic item cannot be used by any monster in your current team!")
    elif len(vt) == 1:
        if language == "zh":
            add("magic_item", "info", "只有一只精灵可以使用所选择的血脉魔法。", monster_ids=vt)
        else:
            add("magic_item", "info", "Only one monster can use the selected magic item.", monster_ids=vt)
    else:
        if language == "zh":
            add("magic_item", "info", "多个精灵可以使用所选择的血脉魔法。", monster_ids=vt)
        else:
            add("magic_item", "info", "Multiple monsters can use the selected magic item.", monster_ids=vt)

    # 4) Redundant typing
    from collections import Counter
    all_types = []
    for analysis in per_monster_analysis:
        m = analysis.user_monster.monster
        all_types.append(m.main_type.id)
        if m.sub_type is not None:
            all_types.append(m.sub_type.id)
    counts = Counter(all_types)
    common_type_ids = [tid for tid, cnt in counts.items() if cnt >= 4]
    if common_type_ids:
        names = [get_localized_name(type_db_map[t], language) for t in common_type_ids]
        if language == "zh":
            add("weakness", "warn",
                f"许多精灵共享这些属性：{', '.join(names)}。这使队伍容易受到特定克制的影响。",
                type_ids=common_type_ids)
        else:
            add("weakness", "warn",
                f"Many monsters share these types: {', '.join(names)}. This increases vulnerability to specific counters.",
                type_ids=common_type_ids)

    # 5) Per-monster checks
    for analysis in per_monster_analysis:
        mid = analysis.user_monster.id
        mname = get_localized_name(analysis.user_monster.monster, language)

        if analysis.energy_profile.avg_energy_cost > 4:
            if language == "zh":
                add("energy", "warn",
                    f"{mname}的技能平均能量消耗很高。建议使用低能量消耗或恢复能量的技能。",
                    monster_ids=[mid])
            else:
                add("energy", "warn",
                    f"{mname}'s moves have high average energy cost. Consider lower-cost or energy-restoring moves.",
                    monster_ids=[mid])

        if analysis.counter_coverage.total_counter_moves == 0:
            if language == "zh":
                add("counters", "warn",
                    f"{mname}没有选择含有应对效果的技能。",
                    monster_ids=[mid])
            else:
                add("counters", "warn",
                    f"{mname} has no counter-effect moves selected.",
                    monster_ids=[mid])

        if analysis.defense_status_move.defense_status_move_count < 2:
            if language == "zh":
                add("defense_status", "warn",
                    f"{mname}的总防御/状态技能少于2个。建议增加更多相应技能以提升灵活性。",
                    monster_ids=[mid])
            else:
                add("defense_status", "warn",
                    f"{mname} has fewer than 2 Defense/Status moves. Consider adding more for flexibility.",
                    monster_ids=[mid])

        # Trait synergy recommendations removed - already covered in per-monster trait synergy analysis
        # for synergy in analysis.trait_synergies:
        #     if synergy.synergy_moves:
        #         move_names = [get_localized_name(move_db_map[x], language) for x in synergy.synergy_moves]
        #         if language == "zh":
        #             add("trait_synergy", "info",
        #                 f"{mname}的特性与以下技能配合良好：{', '.join(move_names)}。",
        #                 monster_ids=[mid], move_ids=synergy.synergy_moves)
        #         else:
        #             add("trait_synergy", "info",
        #                 f"{mname}'s trait works well with: {', '.join(move_names)}.",
        #                 monster_ids=[mid], move_ids=synergy.synergy_moves)

    # 6) Role diversity
    styles = [getattr(a.user_monster.monster, "preferred_attack_style", None) for a in per_monster_analysis]
    if len(set(styles)) == 1 and styles[0]:
        if language == "zh":
            add("general", "warn", f"所有精灵都是{styles[0]}风格的攻击者。这可能使队伍变得可预测。")
        else:
            add("general", "warn", f"All monsters are {styles[0]}-style attackers. This may make the team predictable.")

    # 7) Stat and role highlights
    stat_roles_en = {
        "hp": "frontline or defensive pivot",
        "phy_atk": "main physical attacker",
        "mag_atk": "main magic attacker",
        "overall_def": "physical or special tank",
        "spd": "pressure role or finisher",
    }

    stat_roles_zh = {
        "hp": "前排或防守核心",
        "phy_atk": "主要物理输出手",
        "mag_atk": "主要魔法输出手",
        "overall_def": "物理或魔法坦克",
        "spd": "压制位或收割手",
    }

    stat_roles = stat_roles_zh if language == "zh" else stat_roles_en

    def best_of(stat, label, role_key=None):
        vals = [(get_localized_name(a.user_monster.monster, language), getattr(a.effective_stats, stat), a.user_monster.id)
                for a in per_monster_analysis]
        if not vals:
            return
        name, value, uid = max(vals, key=lambda x: x[1])
        role_txt = stat_roles.get(role_key or stat)
        if language == "zh":
            role_suffix = f"建议将其作为你的{role_txt}。" if role_txt else ""
            add(
                "stat_highlight",
                "info",
                f"{name}拥有最高的{label}（{value}）。{role_suffix}",
                monster_ids=[uid],
            )
        else:
            role_suffix = f" Consider using it as your {role_txt}." if role_txt else ""
            add(
                "stat_highlight",
                "info",
                f"{name} has the highest {label} ({value}).{role_suffix}",
                monster_ids=[uid],
            )

    best_of("hp", "生命值" if language == "zh" else "HP")
    best_of("phy_atk", "物理攻击" if language == "zh" else "Physical Attack")
    best_of("mag_atk", "魔法攻击" if language == "zh" else "Magic Attack")
    # overall defense = phy_def + mag_def
    vals_def = [
        (get_localized_name(a.user_monster.monster, language),
         a.effective_stats.phy_def + a.effective_stats.mag_def,
         a.user_monster.id)
        for a in per_monster_analysis
    ]
    if vals_def:
        name, value, uid = max(vals_def, key=lambda x: x[1])
        role_txt = stat_roles['overall_def']
        if language == "zh":
            add(
                "stat_highlight",
                "info",
                f"{name}拥有最高的总防御（{value}）。建议将其作为你的{role_txt}。",
                monster_ids=[uid],
            )
        else:
            add(
                "stat_highlight",
                "info",
                f"{name} has the highest Total Defense ({value}). Consider using it as your {role_txt}.",
                monster_ids=[uid],
            )
    best_of("spd", "速度" if language == "zh" else "Speed")

    return recs


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
            models.User.is_guest == True
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
    db.commit()
    db.refresh(guest)

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
        normalized_email = email_info.normalized
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

        db.commit()
        db.refresh(user)

    # Case 2: New registration (no guest account)
    else:
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
        )

        db.add(user)
        db.commit()
        db.refresh(user)

    # Send verification email
    email_sent = await send_verification_email(user.email, verification_token)
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
    response: Response,
):
    """
    Reset device ID cookie to a new value.

    Used for "Clear Guest Data" functionality:
    - Generates a new device_id
    - Old guest account becomes inaccessible (orphaned)
    - User can create a fresh guest account

    This endpoint:
    - Does NOT require authentication
    - Sets a new httpOnly device_id cookie
    - Resets cross-account daily caps for the new device
    """
    # Generate new device_id
    new_device_id = str(uuid.uuid4())

    # Set new cookie
    response.set_cookie(
        key=DEVICE_ID_COOKIE_NAME,
        value=new_device_id,
        max_age=DEVICE_ID_COOKIE_MAX_AGE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        domain=COOKIE_DOMAIN,
        path="/",
    )

    logger.info(f"Reset device_id to {new_device_id[:12]}...")

    return {"message": "Device ID reset successfully", "device_id": new_device_id[:8] + "..."}


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
    user = db.query(models.User).filter(models.User.email == email_data.email).first()

    if user and not user.is_guest:
        # Generate reset token (valid for 1 hour)
        reset_token = secrets.token_urlsafe(32)
        user.password_reset_token = reset_token
        user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()

        # Send password reset email
        email_sent = await send_password_reset_email(user.email, reset_token)
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
@limiter.limit("3/hour")
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
    email_sent = await send_email_change_verification(user.pending_email, token)
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
    - email_verified is reset to False (requires re-verification in Phase 7A)
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

    # Reset email verification status (Phase 7A)
    user.email_verified = False

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
    email_sent = await send_verification_email(user.email, verification_token)
    logger.info(f"Verification email resent for user {user.id} ({user.email}), email_sent={email_sent}")

    # Build response
    response_data = {
        "message": "Verification email sent. Please check your inbox."
    }

    # DEV ONLY: Include token for testing (if SMTP not configured)
    if ENVIRONMENT == "development" and not email_sent:
        response_data["debug_token"] = verification_token

    return response_data


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
        # Anonymous user - track by device_id and IP
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
        
    # Enforce deterministic order
    query = query.order_by(models.Monster.id.asc())
    
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

    monsters_by_id = {m.id: m for m in monsters}
    depth_map = {row.id: row.depth for row in nodes_data}

    # 5. Build tree structure organized by stages
    stages_dict = defaultdict(list)

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

    # 7. Calculate metadata
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
        raise HTTPException(status_code=404, detail="Monster not found")

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
    limit: int = Query(468, ge=1, le=468),
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


@app.get("/traits", response_model=List[schemas.TraitOut])
def get_traits(db: Session = Depends(get_db)):
    return db.query(models.Trait).order_by(models.Trait.id).all()


@app.get("/types", response_model=List[schemas.TypeOut])
def get_types(db: Session = Depends(get_db)):
    return db.query(models.Type).order_by(models.Type.id).all()


@app.get("/personalities", response_model=List[schemas.PersonalityOut])
def get_personalities(db: Session = Depends(get_db)):
    return db.query(models.Personality).order_by(models.Personality.id).all()


@app.get("/magic_items", response_model=List[schemas.MagicItemOut])
def get_magic_items(db: Session = Depends(get_db)):
    return db.query(models.MagicItem).order_by(models.MagicItem.id).all()


@app.get("/game_terms", response_model=List[schemas.GameTermOut])
def get_game_terms(db: Session = Depends(get_db)):
    return db.query(models.GameTerm).order_by(models.GameTerm.id).all()


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
    db.commit()

    # Re-fetch with relationships for output schema
    db.refresh(db_team)

    logger.info(f"Created team {db_team.id} for user {current_user.id}")

    return db_team

# -------- Cache Key Generation --------

def generate_monster_cache_key(monster_id: int, move_ids: tuple, language: str) -> str:
    """
    Generate a unique cache key for a monster's trait synergy analysis.

    Uses "llm_cache:" namespace for safe cache clearing without affecting
    token revocations, rate limits, etc.
    """
    # Create a stable string representation of the monster configuration
    key_parts = [
        f"m:{monster_id}",
        f"mv:{'-'.join(map(str, sorted(move_ids)))}",
        f"lang:{language}"
    ]
    key_str = "|".join(key_parts)
    # Hash to keep key size manageable
    return f"llm_cache:monster_trait:{hashlib.md5(key_str.encode()).hexdigest()}"

def generate_team_cache_key(team_data: schemas.TeamCreate, language: str) -> str:
    """
    Generate a unique cache key for team-wide synergy analysis.

    Uses "llm_cache:" namespace for safe cache clearing without affecting
    token revocations, rate limits, etc.
    """
    # Include magic item in the key (different magic item = different team)
    key_parts = [f"magic:{team_data.magic_item_id}"]

    # Add each monster's configuration (using simplified monster cache keys)
    monster_keys = []
    legacy_type_ids = []
    for um in team_data.user_monsters:
        monster_key = generate_monster_cache_key(
            um.monster_id,
            (um.move1_id, um.move2_id, um.move3_id, um.move4_id),
            language
        )
        monster_keys.append(monster_key)
        legacy_type_ids.append(um.legacy_type_id)

    # Sort monster keys to ensure consistent cache key regardless of order
    # Note: We sort indices to maintain legacy_type alignment with monster_keys
    sorted_indices = sorted(range(len(monster_keys)), key=lambda i: monster_keys[i])
    sorted_monster_keys = [monster_keys[i] for i in sorted_indices]
    sorted_legacy_types = [legacy_type_ids[i] for i in sorted_indices]

    key_parts.extend(sorted_monster_keys)

    # Add legacy types explicitly (needed for magic item analysis)
    key_parts.append(f"legacy:{'-'.join(map(str, sorted_legacy_types))}")

    key_str = "|".join(key_parts)
    return f"llm_cache:team_synergy:{hashlib.md5(key_str.encode()).hexdigest()}"


def generate_team_composition_hash(team_data: schemas.TeamCreate) -> str:
    """
    Generate language-independent hash of team composition for rate limiting.

    This hash is used to track rate limits per unique team composition,
    regardless of language. This prevents bypassing rate limits by switching
    between English and Chinese for the same team.

    Note: Personality and talent are excluded as they no longer affect LLM analysis.
    Legacy type is included as it affects team-wide analysis (magic items).
    """
    parts = [
        f"mi:{team_data.magic_item_id}",
    ]

    # Sort user_monsters by monster_id to ensure consistent hash regardless of order
    sorted_monsters = sorted(team_data.user_monsters, key=lambda x: x.monster_id)

    for um in sorted_monsters:
        # Create a string representation of each monster's configuration
        # Note: language, personality, and talent are NOT included
        monster_str = (
            f"m:{um.monster_id}|l:{um.legacy_type_id}|"
            f"mv:{'-'.join(map(str, sorted([um.move1_id, um.move2_id, um.move3_id, um.move4_id])))}"
        )
        parts.append(monster_str)

    # Hash and return first 16 characters (sufficient for rate limiting uniqueness)
    full_hash = hashlib.md5("|".join(parts).encode()).hexdigest()
    return full_hash[:16]


async def check_if_all_cached(team_data: schemas.TeamCreate, language: str) -> bool:
    """
    Pre-flight cache check to determine if analysis can bypass rate limiting.

    Returns True if ALL 7 LLM calls (6 monster + 1 team) would hit cache.
    Returns False if ANY call would be a cache miss.

    This allows cached analyses to be served instantly without rate limiting.
    """
    # Check all 6 monster cache keys
    for um in team_data.user_monsters:
        monster_key = generate_monster_cache_key(
            um.monster_id,
            (um.move1_id, um.move2_id, um.move3_id, um.move4_id),
            language
        )
        # Use await for Redis async get
        cached_value = await redis_cache.get(monster_key)
        if cached_value is None:
            logger.debug(f"Cache miss detected for monster key: {monster_key[:50]}...")
            return False  # At least one cache miss

    # Check team-wide cache key
    team_key = generate_team_cache_key(team_data, language)
    cached_value = await redis_cache.get(team_key)
    if cached_value is None:
        logger.debug(f"Cache miss detected for team key: {team_key[:50]}...")
        return False  # Team synergy cache miss

    logger.info("All cache keys found - bypassing rate limit for fully cached analysis")
    return True  # All 7 calls are cached


# -------- Shared Analysis Logic --------

async def _perform_team_analysis(
    team_data: schemas.TeamCreate,
    language: str,
    db: Session
) -> schemas.TeamAnalysisOut:
    """
    Core team analysis logic shared by both endpoints.
    This function does NOT have rate limiting - that's applied at the endpoint level.
    """
    start_time = time.time()

    # team_data is TeamCreate (with 6 UserMonsterCreate)

    # --- Helper: Call LLM with Caching ---
    async def call_llm(
        prompt: str,
        cache_key: str,
        context: str = None,
        monster_name: str = None,
    ):
        """
        Call LLM with caching support.

        Wrapper for backward compatibility - delegates to generate_analysis_json.
        """
        # Extract team hash from cache key for logging
        team_hash = cache_key[:50] if cache_key else None

        return await generate_analysis_json(
            prompt=prompt,
            cache_key=cache_key,
            llm_cache=redis_cache,  # Use Redis cache with stampede protection
            temperature=None,  # Use default from config
            context=context,
            team_hash=team_hash,
            language=language,
            monster_name=monster_name,
        )

    # === EFFICIENT DATA LOADING ===
    logger.debug("Start loading data for analysis...")
    monster_ids_to_load = {um.monster_id for um in team_data.user_monsters}
    monster_db_map = {m.id: m for m in db.query(models.Monster).filter(models.Monster.id.in_(monster_ids_to_load)).all()}
    logger.debug(f"Loaded monsters: {len(monster_db_map)}")

    # Validate all monsters were found
    missing_monsters = monster_ids_to_load - set(monster_db_map.keys())
    if missing_monsters:
        raise HTTPException(status_code=400, detail=f"Monster IDs not found: {sorted(missing_monsters)}")

    logger.debug("Loading moves...")
    move_ids_to_load = set()
    for um in team_data.user_monsters:
        move_ids_to_load.update([um.move1_id, um.move2_id, um.move3_id, um.move4_id])
    move_db_map = {m.id: m for m in db.query(models.Move).filter(models.Move.id.in_(move_ids_to_load)).all()}
    logger.debug(f"Loaded moves: {len(move_db_map)}")

    # Validate all moves were found
    missing_moves = move_ids_to_load - set(move_db_map.keys())
    if missing_moves:
        raise HTTPException(status_code=400, detail=f"Move IDs not found: {sorted(missing_moves)}")

    logger.debug("Loading traits...")
    trait_ids_to_load = {m.trait_id for m in monster_db_map.values()}
    trait_db_map = {t.id: t for t in db.query(models.Trait).filter(models.Trait.id.in_(trait_ids_to_load)).all()}
    logger.debug(f"Loaded traits: {len(trait_db_map)}")

    logger.debug("Loading types...")
    type_db_map = {
        t.id: t
        for t in db.query(models.Type)
        .options(
            joinedload(models.Type.effective_against),
            joinedload(models.Type.weak_against),
        )
        .all()
    }
    logger.debug(f"Loaded types: {len(type_db_map)}")

    logger.debug("Loading personalities...")
    personality_ids_to_load = {um.personality_id for um in team_data.user_monsters}
    personality_db_map = {p.id: p for p in db.query(models.Personality).filter(models.Personality.id.in_(personality_ids_to_load)).all()}
    logger.debug(f"Loaded personalities: {len(personality_db_map)}")

    logger.debug("Loading magic item and game terms...")
    if not team_data.magic_item_id:
        raise HTTPException(status_code=400, detail="Magic item is required to analyze a team.")
    magic_item = (db.query(models.MagicItem).filter(models.MagicItem.id == team_data.magic_item_id).first())
    if not magic_item:
        raise HTTPException(status_code=400, detail=f"Magic item with ID {team_data.magic_item_id} not found")

    # Create magic_item_db_map with the selected magic item (may be expanded with referenced magic items later)
    magic_item_db_map = {magic_item.id: magic_item}

    # Load game terms as a map for efficient lookup (used for reference resolution)
    game_term_db_map = {gt.id: gt for gt in db.query(models.GameTerm).all()}
    logger.debug(f"Loaded game terms: {len(game_term_db_map)}")

    logger.debug("Finish loading data for analysis!")

    # === CONCURRENT LLM ANALYSIS ===
    logger.debug("Start creating prompt for LLM analysis...")
    logger.info(f"Language received: {language}")

    llm_tasks = []

    # Per-monster trait synergy analysis
    for um in team_data.user_monsters:
        base_monster = monster_db_map[um.monster_id]
        trait = trait_db_map[base_monster.trait_id]
        selected_moves = [move_db_map[um.move1_id], move_db_map[um.move2_id], move_db_map[um.move3_id], move_db_map[um.move4_id]]
        preferred_attack_style = getattr(base_monster, "preferred_attack_style", "Both")

        # Get type and personality information
        legacy_type = type_db_map[um.legacy_type_id]
        main_type = type_db_map[base_monster.main_type_id]
        sub_type = type_db_map[base_monster.sub_type_id] if base_monster.sub_type_id else None
        personality = personality_db_map[um.personality_id]

        # Resolve dynamic move properties for LLM prompt
        # Create copies with resolved properties for Willpower Impact
        resolved_moves_for_prompt = []
        for move in selected_moves:
            resolved_props = resolve_dynamic_move_properties(move, um, base_monster, personality, um.talent, type_db_map)
            # Create a shallow copy and update properties if needed
            if resolved_props['type'] != move.move_type or resolved_props['category'] != move.move_category:
                move_copy = type('Move', (), {})()
                move_copy.__dict__.update(move.__dict__)
                move_copy.move_type = resolved_props['type']
                move_copy.move_category = resolved_props['category']
                resolved_moves_for_prompt.append(move_copy)
            else:
                resolved_moves_for_prompt.append(move)

        # Resolve references PER MONSTER
        if ENABLE_REFERENCE_RESOLUTION:
            entities_for_this_monster = [trait] + resolved_moves_for_prompt
            resolved_refs_per_monster = reference_resolver.resolve_references_for_prompt(entities_for_this_monster, language, db)
            game_terms_per_monster = [game_term_db_map[gt_id] for gt_id in sorted(resolved_refs_per_monster.game_terms)]

            # Load any referenced moves that aren't already in move_db_map
            missing_move_ids_per_monster = resolved_refs_per_monster.moves - set(move_db_map.keys())
            if missing_move_ids_per_monster:
                logger.debug(f"Loading {len(missing_move_ids_per_monster)} referenced moves for monster {get_localized_name(base_monster, language)}: {sorted(missing_move_ids_per_monster)}")
                missing_moves = db.query(models.Move).filter(models.Move.id.in_(missing_move_ids_per_monster)).all()
                for move in missing_moves:
                    move_db_map[move.id] = move

            referenced_moves_per_monster = [move_db_map[m_id] for m_id in sorted(resolved_refs_per_monster.moves) if m_id in move_db_map]

            # Load any referenced monsters that aren't already in monster_db_map
            missing_monster_ids_per_monster = resolved_refs_per_monster.monsters - set(monster_db_map.keys())
            if missing_monster_ids_per_monster:
                logger.debug(f"Loading {len(missing_monster_ids_per_monster)} referenced monsters for monster {get_localized_name(base_monster, language)}: {sorted(missing_monster_ids_per_monster)}")
                missing_monsters = db.query(models.Monster).filter(models.Monster.id.in_(missing_monster_ids_per_monster)).all()
                for monster in missing_monsters:
                    monster_db_map[monster.id] = monster

            referenced_monsters_per_monster = [monster_db_map[mon_id] for mon_id in sorted(resolved_refs_per_monster.monsters) if mon_id in monster_db_map]

            # Load any referenced traits that aren't already in trait_db_map
            missing_trait_ids_per_monster = resolved_refs_per_monster.traits - set(trait_db_map.keys())
            if missing_trait_ids_per_monster:
                logger.debug(f"Loading {len(missing_trait_ids_per_monster)} referenced traits for monster {get_localized_name(base_monster, language)}: {sorted(missing_trait_ids_per_monster)}")
                missing_traits = db.query(models.Trait).filter(models.Trait.id.in_(missing_trait_ids_per_monster)).all()
                for trait_obj in missing_traits:
                    trait_db_map[trait_obj.id] = trait_obj

            # Load any referenced magic items that aren't already in magic_item_db_map
            missing_magic_item_ids_per_monster = resolved_refs_per_monster.magic_items - set(magic_item_db_map.keys())
            if missing_magic_item_ids_per_monster:
                logger.debug(f"Loading {len(missing_magic_item_ids_per_monster)} referenced magic items for monster {get_localized_name(base_monster, language)}: {sorted(missing_magic_item_ids_per_monster)}")
                missing_magic_items = db.query(models.MagicItem).filter(models.MagicItem.id.in_(missing_magic_item_ids_per_monster)).all()
                for mi in missing_magic_items:
                    magic_item_db_map[mi.id] = mi

            logger.info(f"Monster {get_localized_name(base_monster, language)}: {len(game_terms_per_monster)} game terms, {len(referenced_moves_per_monster)} referenced moves, {len(referenced_monsters_per_monster)} referenced monsters")
        else:
            game_terms_per_monster = list(game_term_db_map.values())
            referenced_moves_per_monster = []
            referenced_monsters_per_monster = []

        # Generate cache key for this monster
        cache_key = generate_monster_cache_key(
            um.monster_id,
            (um.move1_id, um.move2_id, um.move3_id, um.move4_id),
            language
        )

        prompt = build_trait_synergy_prompt(base_monster, trait, resolved_moves_for_prompt, game_terms_per_monster, referenced_moves_per_monster, referenced_monsters_per_monster, main_type, sub_type, type_db_map, language)

        # Get monster name for logging
        monster_name = get_localized_name(base_monster, language)

        llm_tasks.append(call_llm(
            prompt=prompt,
            cache_key=cache_key,
            context="trait_synergy",
            monster_name=monster_name,
        ))

    # Resolve references for TEAM (all entities combined)
    if ENABLE_REFERENCE_RESOLUTION:
        all_entities_for_team = []
        for um in team_data.user_monsters:
            base_monster = monster_db_map[um.monster_id]
            trait = trait_db_map[base_monster.trait_id]
            selected_moves = [move_db_map[um.move1_id], move_db_map[um.move2_id], move_db_map[um.move3_id], move_db_map[um.move4_id]]
            all_entities_for_team.append(trait)
            all_entities_for_team.extend(selected_moves)

        # Include magic item description for reference resolution
        all_entities_for_team.append(magic_item)

        resolved_refs_team = reference_resolver.resolve_references_for_prompt(all_entities_for_team, language, db)
        game_terms_team = [game_term_db_map[gt_id] for gt_id in sorted(resolved_refs_team.game_terms)]

        # Load any referenced moves that aren't already in move_db_map
        missing_move_ids = resolved_refs_team.moves - set(move_db_map.keys())
        if missing_move_ids:
            logger.info(f"Loading {len(missing_move_ids)} referenced moves not in team: {sorted(missing_move_ids)}")
            missing_moves = db.query(models.Move).filter(models.Move.id.in_(missing_move_ids)).all()
            for move in missing_moves:
                move_db_map[move.id] = move

        # Filter out Willpower Impact from referenced moves - it's a magic-item-generated move, not a regular referenced move
        # It will be explained in the Willpower Enhancement section instead
        referenced_moves_team = [
            move_db_map[m_id] for m_id in sorted(resolved_refs_team.moves)
            if m_id in move_db_map and move_db_map[m_id].name != "Willpower Impact"
        ]

        # Load any referenced monsters that aren't already in monster_db_map
        missing_monster_ids_team = resolved_refs_team.monsters - set(monster_db_map.keys())
        if missing_monster_ids_team:
            logger.info(f"Loading {len(missing_monster_ids_team)} referenced monsters not in team: {sorted(missing_monster_ids_team)}")
            missing_monsters = db.query(models.Monster).filter(models.Monster.id.in_(missing_monster_ids_team)).all()
            for monster in missing_monsters:
                monster_db_map[monster.id] = monster

        referenced_monsters_team = [monster_db_map[mon_id] for mon_id in sorted(resolved_refs_team.monsters) if mon_id in monster_db_map]

        # Load any referenced traits that aren't already in trait_db_map
        missing_trait_ids_team = resolved_refs_team.traits - set(trait_db_map.keys())
        if missing_trait_ids_team:
            logger.info(f"Loading {len(missing_trait_ids_team)} referenced traits not in team: {sorted(missing_trait_ids_team)}")
            missing_traits = db.query(models.Trait).filter(models.Trait.id.in_(missing_trait_ids_team)).all()
            for trait_obj in missing_traits:
                trait_db_map[trait_obj.id] = trait_obj

        # Load any referenced magic items that aren't already in magic_item_db_map
        missing_magic_item_ids_team = resolved_refs_team.magic_items - set(magic_item_db_map.keys())
        if missing_magic_item_ids_team:
            logger.info(f"Loading {len(missing_magic_item_ids_team)} referenced magic items not in team: {sorted(missing_magic_item_ids_team)}")
            missing_magic_items = db.query(models.MagicItem).filter(models.MagicItem.id.in_(missing_magic_item_ids_team)).all()
            for mi in missing_magic_items:
                magic_item_db_map[mi.id] = mi

        logger.info(f"Team analysis: {len(game_terms_team)} game terms, {len(referenced_moves_team)} referenced moves, {len(referenced_monsters_team)} referenced monsters")
    else:
        game_terms_team = list(game_term_db_map.values())
        referenced_moves_team = []
        referenced_monsters_team = []

    # Team-wide synergy analysis
    team_cache_key = generate_team_cache_key(team_data, language)
    team_synergy_prompt = build_team_synergy_prompt(team_data.user_monsters, monster_db_map, move_db_map, type_db_map, trait_db_map, magic_item, game_terms_team, referenced_moves_team, referenced_monsters_team, language, db)
    llm_tasks.append(call_llm(
        prompt=team_synergy_prompt,
        cache_key=team_cache_key,
        context="team_synergy",
        monster_name=None,  # Team-wide analysis, no specific monster
    ))

    # Gather all LLM results, capturing exceptions to handle errors gracefully
    llm_results = await asyncio.gather(*llm_tasks, return_exceptions=True)

    # Categorize errors by type for better handling
    quota_errors = []
    rate_limit_errors = []
    server_errors = []
    auth_errors = []
    other_errors = []
    successful_calls = 0

    for i, result in enumerate(llm_results):
        if isinstance(result, Exception):
            error_msg = str(result).lower()

            # Quota exhaustion (Gemini, OpenAI, etc.)
            if any(pattern in error_msg for pattern in ["429", "resource_exhausted", "quota", "insufficient_quota"]):
                quota_errors.append((i, result))
            # Rate limiting (DeepSeek, OpenAI)
            elif any(pattern in error_msg for pattern in ["rate_limit", "too_many_requests", "requests per"]):
                rate_limit_errors.append((i, result))
            # Server errors (500, 502, 503, timeout)
            elif any(pattern in error_msg for pattern in ["500", "502", "503", "504", "timeout", "timed out", "unavailable"]):
                server_errors.append((i, result))
            # Authentication errors (401, 403, invalid API key)
            elif any(pattern in error_msg for pattern in ["401", "403", "unauthorized", "forbidden", "invalid.*key", "api.*key"]):
                auth_errors.append((i, result))
            else:
                other_errors.append((i, result))
        else:
            successful_calls += 1

    # Fail fast only for CRITICAL errors that affect all requests
    # 1. Authentication errors (most critical - prevents all future requests)
    if auth_errors:
        logger.error(f"Authentication failed: {len(auth_errors)} of {len(llm_tasks)} LLM calls failed due to auth issues")
        if language == "zh":
            error_detail = "API 认证失败。请检查 API 密钥配置。"
        else:
            error_detail = "API authentication failed. Please check your API key configuration."
        raise HTTPException(status_code=401, detail=error_detail)

    # 2. Quota exhaustion (common with free tiers) - only fail if ALL calls failed
    if quota_errors and successful_calls == 0:
        logger.error(f"Quota exhausted: {len(quota_errors)} of {len(llm_tasks)} LLM calls failed due to quota limits")
        if language == "zh":
            error_detail = f"API 配额已用尽。当前提供商: {LLM_PROVIDER}。请稍后重试或检查配额限制。"
        else:
            error_detail = f"API quota exhausted for provider: {LLM_PROVIDER}. Please try again later or check your quota limits."
        raise HTTPException(status_code=429, detail=error_detail)

    # For TRANSIENT errors (server issues, rate limits, etc.), allow partial success
    # Replace failed results with error marker dicts so they can be retried later
    total_errors = len(server_errors) + len(rate_limit_errors) + len(other_errors) + len(quota_errors)

    if total_errors > 0:
        # Log warning about partial failure
        logger.warning(
            f"Partial analysis success: {successful_calls}/{len(llm_tasks)} LLM calls succeeded. "
            f"Errors: {len(server_errors)} server, {len(rate_limit_errors)} rate limit, "
            f"{len(quota_errors)} quota, {len(other_errors)} other"
        )

        # Replace exception results with error marker dicts
        for idx, error in server_errors + rate_limit_errors + quota_errors + other_errors:
            error_msg = str(error)
            logger.error(f"LLM call {idx} failed: {error_msg[:200]}")

            # Create error marker dict (will NOT be cached since exception was raised)
            if language == "zh":
                llm_results[idx] = {
                    "synergy_moves": [],
                    "recommendation": [f"⚠️ 分析暂时失败，请重新分析以重试。错误: {error_msg[:100]}"],
                    "_error": True,  # Marker for failed result
                    "_error_type": "transient"
                }
            else:
                llm_results[idx] = {
                    "synergy_moves": [],
                    "recommendation": [f"⚠️ Analysis temporarily failed, please re-analyze to retry. Error: {error_msg[:100]}"],
                    "_error": True,  # Marker for failed result
                    "_error_type": "transient"
                }

        # Log quota tracking info
        logger.info(f"Quota used: {successful_calls} successful LLM calls out of {len(llm_tasks)} total")

    logger.debug("Finish creating prompt for LLM analysis!")

    # Build UserMonsterOuts and compute per-monster analysis
    logger.debug("Start per-monster analysis...")
    user_monster_outs = []
    per_monster_analysis = []
    for i, um in enumerate(team_data.user_monsters):
        base_monster = monster_db_map[um.monster_id]
        personality = personality_db_map[um.personality_id]
        legacy_type = type_db_map[um.legacy_type_id]
        trait = trait_db_map[base_monster.trait_id]
        move1 = move_db_map[um.move1_id]
        move2 = move_db_map[um.move2_id]
        move3 = move_db_map[um.move3_id]
        move4 = move_db_map[um.move4_id]
        selected_moves = [move1, move2, move3, move4]
        talent = um.talent
        llm_result = llm_results[i]
        
        # Map move names to ids for schema output (handle both English and localized names)
        move_name_to_id = {m.name: m.id for m in selected_moves}
        # Also add localized names to the mapping
        for m in selected_moves:
            localized_name = get_localized_name(m, language)
            if localized_name != m.name:
                move_name_to_id[localized_name] = m.id
        synergy_moves = [move_name_to_id[name] for name in llm_result.get("synergy_moves", []) if name in move_name_to_id]

        trait_synergy_finding = schemas.TraitSynergyFinding(
            monster_id=base_monster.id,
            trait=schemas.TraitOut.model_validate(trait),
            synergy_moves=synergy_moves,
            recommendation=llm_result.get("recommendation", [])
        )
            
        # Call the top-level helper functions
        effective_stats = compute_effective_stats(base_monster, personality, talent)
        energy_profile = compute_energy_profile(selected_moves)
        counter_coverage = compute_counter_coverage(selected_moves)
        defense_status_move = compute_defense_status_move(selected_moves)

        # Resolve dynamic move properties for display
        move1_props = resolve_dynamic_move_properties(move1, um, base_monster, personality, talent, type_db_map)
        move2_props = resolve_dynamic_move_properties(move2, um, base_monster, personality, talent, type_db_map)
        move3_props = resolve_dynamic_move_properties(move3, um, base_monster, personality, talent, type_db_map)
        move4_props = resolve_dynamic_move_properties(move4, um, base_monster, personality, talent, type_db_map)

        # Build UserMonsterOut
        def to_monster_lite_out(monster, type_db_map):
            return schemas.MonsterLiteOut(
                id=monster.id,
                name=monster.name,
                form=monster.form,
                main_type=schemas.TypeOut(**type_db_map[monster.main_type_id].__dict__),
                sub_type=schemas.TypeOut(**type_db_map[monster.sub_type_id].__dict__) if monster.sub_type_id else None,
                leader_potential=getattr(monster, "leader_potential", False),
                is_leader_form=monster.is_leader_form,
                preferred_attack_style = getattr(monster, "preferred_attack_style", "Both"),
                localized=monster.localized
            )

        # Helper to create MoveOut with resolved properties
        def to_move_out(move, resolved_props):
            move_dict = move.__dict__.copy()
            move_dict['move_type'] = resolved_props['type']
            move_dict['move_category'] = resolved_props['category']
            # Handle the type_id field
            if resolved_props['type']:
                move_dict['move_type_id'] = resolved_props['type'].id
            return schemas.MoveOut(**move_dict)

        user_monster_out = schemas.UserMonsterOut(
            id=i,
            monster=to_monster_lite_out(base_monster, type_db_map),
            personality=schemas.PersonalityOut(**personality.__dict__),
            legacy_type=schemas.TypeOut(**legacy_type.__dict__),
            move1=to_move_out(move1, move1_props),
            move2=to_move_out(move2, move2_props),
            move3=to_move_out(move3, move3_props),
            move4=to_move_out(move4, move4_props),
            talent=schemas.TalentOut(id=i, **talent.model_dump()),
        )
        
        user_monster_outs.append(user_monster_out)

        # Build MonsterAnalysisOut
        monster_analysis = schemas.MonsterAnalysisOut(
            user_monster=user_monster_out,
            effective_stats=effective_stats,
            energy_profile=energy_profile,
            counter_coverage=counter_coverage,
            defense_status_move=defense_status_move,
            trait_synergies=[trait_synergy_finding]
        )
        per_monster_analysis.append(monster_analysis)

    logger.debug("Finish per-monster analysis!")

    # Call the top-level helper functions
    logger.debug("Start team-level analysis...")
    type_coverage = compute_type_coverage(team_data.user_monsters, move_db_map, monster_db_map, type_db_map, personality_db_map, magic_item)
    magic_item_eval_dict = compute_magic_item_eval(magic_item, user_monster_outs, type_db_map)
    magic_item_out = schemas.MagicItemOut(**magic_item.__dict__)
    magic_item_eval = schemas.MagicItemEvaluation(
        chosen_item=magic_item_out,
        valid_targets=magic_item_eval_dict["valid_targets"],
        best_target_monster_id=magic_item_eval_dict.get("best_target_monster_id"),
        reasoning=magic_item_eval_dict.get("reasoning"),
    )

    recs_struct = generate_recommendations(
        per_monster_analysis,
        type_coverage,
        magic_item_eval,
        move_db_map,
        type_db_map,
        language
    )

    # Extract team synergy from the last LLM result
    team_synergy_result = llm_results[-1]  # Last result is team synergy
    team_synergy = schemas.TeamSynergyRecommendation(
        team_archetype=team_synergy_result.get("team_archetype", []),
        action_priority=team_synergy_result.get("action_priority", []),
        switching_strategy=team_synergy_result.get("switching_strategy", []),
        magic_item_usage=team_synergy_result.get("magic_item_usage", []),
        overall_strategy=team_synergy_result.get("overall_strategy", [])
    )

    team_out = schemas.TeamOut(
        id=0,
        name=team_data.name,
        user_monsters=user_monster_outs,
        magic_item=magic_item_out,
    )
    result = schemas.TeamAnalysisOut(
        team=team_out,
        per_monster=per_monster_analysis,
        type_coverage=type_coverage,
        magic_item_eval=magic_item_eval,
        recommendations=[r.message for r in recs_struct],
        recommendations_structured=recs_struct,
        team_synergy=team_synergy,
    )

    logger.debug("Finish team-level analysis!")
    elapsed = time.time() - start_time
    logger.info(f"Team analysis took {elapsed:.3f} seconds")
    return result


# -------- Helper to apply rate limiting --------

@analysis_rate_limit()
async def _apply_rate_limit_check(request: Request):
    """
    Helper function to check rate limit.
    Raises RateLimitExceeded if limit is exceeded.
    Requires Request object for IP-based rate limiting.
    """
    pass


# -------- Analyze Team (Inline) --------

@app.post("/team/analyze", response_model=schemas.TeamAnalysisOut)
async def analyze_team(
    req: schemas.TeamAnalyzeInlineRequest,
    request: Request,
    user_or_anon: tuple = Depends(get_user_or_anonymous),
    db: Session = Depends(get_db)
):
    """Analyze a team configuration (inline data from request).

    Three-tier rate limiting:
    - Anonymous: 1/day via device_id + IP tracking
    - Guest: 3/day via user.id tracking
    - Registered: 5/day (free) or more (premium) via user.id tracking
    - IP-based rate limit also applies (prevents rapid requests)
    - Cached analyses bypass ALL rate limits
    """
    user, device_id, client_ip = user_or_anon

    # Generate language-independent team composition hash
    team_hash = generate_team_composition_hash(req.team)

    # Check if fully cached - cached analyses bypass all rate limits
    is_fully_cached = await check_if_all_cached(req.team, req.language)

    if not is_fully_cached:
        # Not cached - check tier-based rate limits

        # 1. Per-user quota check based on user type
        if user is None:
            # Anonymous user - check anonymous limits (1/day)
            await check_anonymous_analysis_limit(device_id, client_ip, req.language)
        else:
            # Authenticated user (guest or registered) - check user limits
            await check_analysis_limit(user, db, req.language)

        # 2. Cross-account device daily cap (prevents multi-account abuse)
        # Premium/unlimited users are exempt
        await check_device_daily_cap(device_id, user)

        # 3. IP daily cap (fallback when device_id missing, also abuse signal)
        if device_id == "unknown-device":
            await check_ip_daily_cap(client_ip, user)

        # 4. IP-based rate limit (prevents analyzing different teams rapidly)
        if not await check_global_ip_rate_limit_async(client_ip):
            logger.warning(
                f"Global rate limit exceeded for {client_ip} analyzing team {team_hash} in {req.language}"
            )
            raise HTTPException(
                status_code=429,
                detail=get_rate_limit_message(req.language)
            )

        # 5. Per-team rate limit (prevents language-switching exploits)
        if not await check_analysis_rate_limit_async(client_ip, team_hash):
            logger.warning(
                f"Per-team rate limit exceeded for {client_ip} analyzing team {team_hash} in {req.language}"
            )
            raise HTTPException(
                status_code=429,
                detail=get_rate_limit_message(req.language)
            )

        # Record this analysis
        logger.info(f"Recording analysis for {client_ip}:{team_hash}")
        await record_analysis_async(client_ip, team_hash)

        # Record tier usage
        if user is None:
            # Anonymous user
            await record_anonymous_analysis(device_id, client_ip)
        else:
            # Authenticated user (guest or registered)
            await record_analysis_usage(user)

        # Record device/IP usage for cross-account caps
        await record_device_and_ip_usage(device_id, client_ip)

    return await _perform_team_analysis(req.team, req.language, db)


# -------- Analyze Team by ID --------

@app.post("/team/analyze_by_id", response_model=schemas.TeamAnalysisOut)
async def analyze_team_by_id(
    req: schemas.TeamAnalyzeByIdRequest,
    request: Request,
    user_or_anon: tuple = Depends(get_user_or_anonymous),
    db: Session = Depends(get_db)
):
    """Analyze a saved team by its ID.

    Three-tier rate limiting (same as /team/analyze):
    - Anonymous: 1/day via device_id + IP tracking
    - Guest: 3/day via user.id tracking
    - Registered: 5/day (free) or more (premium) via user.id tracking
    - Cached analyses bypass ALL rate limits
    """
    user, device_id, client_ip = user_or_anon

    # Load the Team, its UserMonsters, Talents, etc. from the DB
    db_team = db.query(models.Team).filter(models.Team.id == req.team_id).first()
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Build TeamCreate-like dict from DB objects
    user_monsters = []
    for um in db_team.user_monsters:
        talent = db.query(models.Talent).filter(models.Talent.monster_instance_id == um.id).first()
        user_monsters.append(
            schemas.UserMonsterCreate(
                monster_id=um.monster_id,
                personality_id=um.personality_id,
                legacy_type_id=um.legacy_type_id,
                move1_id=um.move1_id,
                move2_id=um.move2_id,
                move3_id=um.move3_id,
                move4_id=um.move4_id,
                talent=schemas.TalentIn(
                    hp_boost=talent.hp_boost,
                    phy_atk_boost=talent.phy_atk_boost,
                    mag_atk_boost=talent.mag_atk_boost,
                    phy_def_boost=talent.phy_def_boost,
                    mag_def_boost=talent.mag_def_boost,
                    spd_boost=talent.spd_boost
                ),
            )
        )
    team_data = schemas.TeamCreate(
        name=db_team.name,
        user_monsters=user_monsters,
        magic_item_id=db_team.magic_item_id
    )

    # Generate language-independent team composition hash
    team_hash = generate_team_composition_hash(team_data)

    # Check if fully cached - cached analyses bypass all rate limits
    is_fully_cached = await check_if_all_cached(team_data, req.language)

    if not is_fully_cached:
        # Not cached - check tier-based rate limits

        # 1. Per-user quota check based on user type
        if user is None:
            # Anonymous user - check anonymous limits (1/day)
            await check_anonymous_analysis_limit(device_id, client_ip, req.language)
        else:
            # Authenticated user (guest or registered) - check user limits
            await check_analysis_limit(user, db, req.language)

        # 2. Cross-account device daily cap (prevents multi-account abuse)
        # Premium/unlimited users are exempt
        await check_device_daily_cap(device_id, user)

        # 3. IP daily cap (fallback when device_id missing, also abuse signal)
        if device_id == "unknown-device":
            await check_ip_daily_cap(client_ip, user)

        # 4. IP-based rate limit (prevents analyzing different teams rapidly)
        if not await check_global_ip_rate_limit_async(client_ip):
            logger.warning(
                f"Global rate limit exceeded for {client_ip} analyzing team {team_hash} (ID: {req.team_id}) in {req.language}"
            )
            raise HTTPException(
                status_code=429,
                detail=get_rate_limit_message(req.language)
            )

        # 5. Per-team rate limit (prevents language-switching exploits)
        if not await check_analysis_rate_limit_async(client_ip, team_hash):
            logger.warning(
                f"Per-team rate limit exceeded for {client_ip} analyzing team {team_hash} (ID: {req.team_id}) in {req.language}"
            )
            raise HTTPException(
                status_code=429,
                detail=get_rate_limit_message(req.language)
            )

        # Record this analysis
        logger.info(f"Recording analysis for {client_ip}:{team_hash}")
        await record_analysis_async(client_ip, team_hash)

        # Record tier usage
        if user is None:
            # Anonymous user
            await record_anonymous_analysis(device_id, client_ip)
        else:
            # Authenticated user (guest or registered)
            await record_analysis_usage(user)

        # Record device/IP usage for cross-account caps
        await record_device_and_ip_usage(device_id, client_ip)

    return await _perform_team_analysis(team_data, req.language, db)

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
    db.commit()
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
# -------- Saved Analysis Helper Functions --------

def save_or_update_analysis(
    team_id: int,
    language: str,
    analysis_data: dict,
    is_from_cache: bool,
    db: Session
) -> models.TeamAnalysis:
    """Save or update analysis for a team (replaces if exists)."""
    existing = (
        db.query(models.TeamAnalysis)
        .filter(
            models.TeamAnalysis.team_id == team_id,
            models.TeamAnalysis.language == language
        )
        .first()
    )

    if existing:
        existing.analysis_data = analysis_data
        existing.is_from_cache = is_from_cache
        existing.created_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    else:
        new_analysis = models.TeamAnalysis(
            team_id=team_id,
            language=language,
            analysis_data=analysis_data,
            is_from_cache=is_from_cache
        )
        db.add(new_analysis)
        db.commit()
        db.refresh(new_analysis)
        return new_analysis

# -------- Saved Analysis Endpoints --------

@app.post("/analysis/save", response_model=schemas.SavedAnalysisOut, tags=["Analysis"])
def save_analysis(
    req: schemas.SaveAnalysisRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save an analysis result for a team. Replaces existing if present.

    SECURITY: Only owner can save analysis for their team.
    """
    team = db.query(models.Team).filter(models.Team.id == req.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # SECURITY: Check ownership
    if team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to save analysis for this team"
        )

    saved = save_or_update_analysis(
        team_id=req.team_id,
        language=req.language,
        analysis_data=req.analysis_data.model_dump(),
        is_from_cache=req.is_from_cache,
        db=db
    )

    return saved

@app.get("/teams/{team_id}/analysis", response_model=schemas.FullSavedAnalysisOut, tags=["Analysis"])
def get_saved_analysis(
    team_id: int,
    language: Literal["en", "zh"] = "en",
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve saved analysis for a team.

    SECURITY: Only owner can view team's analysis.
    """
    # Check team ownership first
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # SECURITY: Check ownership
    if team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this team's analysis"
        )

    saved = (
        db.query(models.TeamAnalysis)
        .filter(
            models.TeamAnalysis.team_id == team_id,
            models.TeamAnalysis.language == language
        )
        .first()
    )

    if not saved:
        raise HTTPException(status_code=404, detail="No saved analysis found for this team")

    return saved

@app.delete("/teams/{team_id}/analysis", status_code=status.HTTP_204_NO_CONTENT, tags=["Analysis"])
def delete_saved_analysis(
    team_id: int,
    language: Literal["en", "zh"] = "en",
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete saved analysis for a team.

    SECURITY: Only owner can delete team's analysis.
    """
    # Check team ownership first
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # SECURITY: Check ownership
    if team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this team's analysis"
        )

    saved = (
        db.query(models.TeamAnalysis)
        .filter(
            models.TeamAnalysis.team_id == team_id,
            models.TeamAnalysis.language == language
        )
        .first()
    )

    if not saved:
        raise HTTPException(status_code=404, detail="No saved analysis found")

    db.delete(saved)
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
            teams_count=teams_count,
            is_admin=is_admin_user(user)
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
        teams_count=teams_count,
        is_admin=is_admin_user(user)
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
    total_analyses = db.query(models.TeamAnalysis).count()

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
        total_analyses=total_analyses,
        users_by_tier=users_by_tier,
        registrations_today=registrations_today,
        registrations_this_week=registrations_this_week,
        registrations_this_month=registrations_this_month
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

    # Find users to delete (not system, not admin)
    users_to_delete = db.query(models.User).filter(
        models.User.is_system == False,
        ~models.User.email.in_(ADMIN_EMAILS) if ADMIN_EMAILS else True
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
