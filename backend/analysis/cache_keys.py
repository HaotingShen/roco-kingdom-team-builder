"""Cache-key generation and the pre-flight cache check.

Extracted verbatim from main.py (2026-07-06 behavior-preserving refactor).
Key semantics are UNCHANGED — including the Willpower-Enhancement signature
that keys team-synergy results by each monster's resolved
Physical/Magic category.
"""
import hashlib
from typing import Optional, List
from sqlalchemy.orm import Session
from backend import models, schemas
from backend.logger import logger
from backend.cache import redis_cache
from backend.analysis.computations import compute_effective_stats


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


def compute_willpower_categories(
    user_monsters,
    monster_db_map: dict,
    personality_db_map: dict,
) -> list[str]:
    """
    Compute each monster's resolved Willpower Impact category ("P"/"M"),
    in the same order as user_monsters.

    The team synergy prompt states whether Willpower Impact becomes a Physical
    or Magic attack for each monster (based on effective phy_atk vs mag_atk,
    which depends on personality AND talent). The team cache key must therefore
    encode this whenever the Willpower Enhancement magic item is selected —
    otherwise two teams differing only in personality/talent would share a
    cached team analysis with the wrong Physical/Magic statements.
    """
    categories = []
    for um in user_monsters:
        monster = monster_db_map[um.monster_id]
        personality = personality_db_map[um.personality_id]
        stats = compute_effective_stats(monster, personality, um.talent)
        categories.append("P" if stats.phy_atk > stats.mag_atk else "M")
    return categories


def generate_team_cache_key(
    team_data: schemas.TeamCreate,
    language: str,
    willpower_categories: Optional[list[str]] = None,
) -> str:
    """
    Generate a unique cache key for team-wide synergy analysis.

    Uses "llm_cache:" namespace for safe cache clearing without affecting
    token revocations, rate limits, etc.

    willpower_categories: per-monster resolved Willpower Impact category
    ("P"/"M"), aligned with team_data.user_monsters. Pass it whenever the
    selected magic item is Willpower Enhancement (effect_code ENHANCE_SPELL);
    it becomes part of the key because the team prompt content depends on it.
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

    # Willpower Impact categories (only for Willpower Enhancement teams),
    # sorted with the same index order to stay stable under monster reordering.
    if willpower_categories is not None:
        sorted_wp = [willpower_categories[i] for i in sorted_indices]
        key_parts.append(f"wp:{'-'.join(sorted_wp)}")

    key_str = "|".join(key_parts)
    return f"llm_cache:team_synergy:{hashlib.md5(key_str.encode()).hexdigest()}"


def _load_willpower_categories_if_needed(
    team_data: schemas.TeamCreate, db: Session
) -> Optional[list[str]]:
    """
    Load just enough data to compute willpower categories for cache keying.

    Returns None when the selected magic item is not Willpower Enhancement
    (the common case — no extra queries beyond the magic item lookup).
    """
    if not team_data.magic_item_id:
        return None
    magic_item = (
        db.query(models.MagicItem)
        .filter(models.MagicItem.id == team_data.magic_item_id)
        .first()
    )
    if not magic_item or magic_item.effect_code != models.MagicEffectCode.ENHANCE_SPELL:
        return None

    monster_ids = {um.monster_id for um in team_data.user_monsters}
    personality_ids = {um.personality_id for um in team_data.user_monsters}
    monster_db_map = {
        m.id: m for m in db.query(models.Monster).filter(models.Monster.id.in_(monster_ids)).all()
    }
    personality_db_map = {
        p.id: p for p in db.query(models.Personality).filter(models.Personality.id.in_(personality_ids)).all()
    }
    # Missing IDs are rejected later with a proper 400 in _perform_team_analysis;
    # here we just skip the signature so the request proceeds to that validation.
    for um in team_data.user_monsters:
        if um.monster_id not in monster_db_map or um.personality_id not in personality_db_map:
            return None
    return compute_willpower_categories(team_data.user_monsters, monster_db_map, personality_db_map)


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


async def check_if_all_cached(team_data: schemas.TeamCreate, language: str, db: Session) -> bool:
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

    # Check team-wide cache key (must match the key _perform_team_analysis
    # uses, including the willpower signature for Willpower Enhancement teams)
    willpower_categories = _load_willpower_categories_if_needed(team_data, db)
    team_key = generate_team_cache_key(team_data, language, willpower_categories)
    cached_value = await redis_cache.get(team_key)
    if cached_value is None:
        logger.debug(f"Cache miss detected for team key: {team_key[:50]}...")
        return False  # Team synergy cache miss

    logger.info("All cache keys found - bypassing rate limit for fully cached analysis")
    return True  # All 7 calls are cached
