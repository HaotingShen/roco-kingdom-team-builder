"""Caching utilities for expensive operations."""

from functools import lru_cache, wraps
from typing import Dict, List, Any, Callable
import time


# In-memory cache for type effectiveness (small, static data)
@lru_cache(maxsize=256)
def get_cached_type_effectiveness(type_id: int, target_type_id: int) -> str:
    """
    Cache type effectiveness lookups.

    Returns: 'effective', 'weak', 'resistant', or 'normal'

    Note: This is a placeholder. The actual implementation should be
    integrated with the database queries in main.py
    """
    # This will be populated by actual database queries
    return "normal"


@lru_cache(maxsize=128)
def get_cached_monster_types(monster_id: int) -> tuple:
    """
    Cache monster type lookups.

    Returns: (main_type_id, sub_type_id, legacy_type_id)

    Note: This is a placeholder for integration with main.py
    """
    # This will be populated by actual database queries
    return (0, 0, 0)


class TimedCache:
    """Simple time-based cache with TTL support."""

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize timed cache.

        Args:
            ttl_seconds: Time to live in seconds (default 5 minutes)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return None

        value, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl_seconds:
            # Expired
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp."""
        self._cache[key] = (value, time.time())

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()

    def delete(self, key: str) -> None:
        """Delete specific key from cache."""
        if key in self._cache:
            del self._cache[key]


# Global cache instance for LLM responses
# LLM responses are expensive, so cache for 1 hour
llm_cache = TimedCache(ttl_seconds=3600)


def cache_llm_response(func: Callable) -> Callable:
    """
    Decorator to cache LLM responses.

    Creates a cache key from the function arguments and caches the result.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Create cache key from arguments
        # For LLM calls, key should include monster_id, trait_id, and move_ids
        cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"

        # Check cache
        cached_result = llm_cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        # Call function and cache result
        result = await func(*args, **kwargs)
        llm_cache.set(cache_key, result)
        return result

    return wrapper


# Cache for frequently accessed game data
game_data_cache = TimedCache(ttl_seconds=600)  # 10 minutes


def invalidate_team_cache(team_id: int) -> None:
    """Invalidate cache entries for a specific team."""
    # Clear any cached analysis for this team
    llm_cache.delete(f"team_analysis:{team_id}")
    game_data_cache.delete(f"team:{team_id}")


def clear_all_caches() -> None:
    """Clear all application caches."""
    llm_cache.clear()
    game_data_cache.clear()
    # Also clear lru_cache decorators
    get_cached_type_effectiveness.cache_clear()
    get_cached_monster_types.cache_clear()
