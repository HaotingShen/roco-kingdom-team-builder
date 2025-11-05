"""Caching utilities for expensive operations."""

from typing import Dict, Any
import time


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
