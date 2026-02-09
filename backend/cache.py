"""Caching utilities for expensive operations."""

from typing import Dict, Any, Optional, Callable, Awaitable
import time
import json
import asyncio
from redis import asyncio as aioredis
from backend.logger import logger


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


class RedisCache:
    """
    Redis-based cache with stampede protection using distributed locks.

    Features:
    - Persistent cache across server restarts
    - Stampede protection: only one request computes a value, others wait
    - TTL support for automatic expiration
    - Graceful fallback on connection errors
    """

    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int = 3600,
        lock_timeout: int = 30,
        lock_blocking_timeout: int = 60,
    ):
        """
        Initialize Redis cache.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
            ttl_seconds: Cache TTL in seconds (default: 1 hour)
            lock_timeout: How long lock is held (default: 30s)
            lock_blocking_timeout: How long to wait for lock (default: 60s)
        """
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.lock_timeout = lock_timeout
        self.lock_blocking_timeout = lock_blocking_timeout
        self._redis: Optional[aioredis.Redis] = None
        self._connected = False

    async def connect(self):
        """Establish Redis connection."""
        if self._redis is not None:
            return

        try:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            # Test connection
            await self._redis.ping()
            self._connected = True
            logger.info(f"Redis cache connected: {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            self._redis = None

    async def disconnect(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._connected = False
            logger.info("Redis cache disconnected")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self._connected or not self._redis:
            return None

        try:
            value = await self._redis.get(key)
            if value is None:
                return None

            # Deserialize JSON
            return json.loads(value)
        except Exception as e:
            logger.error(f"Redis GET error for key {key[:50]}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL."""
        if not self._connected or not self._redis:
            return False

        try:
            ttl = ttl or self.ttl_seconds
            # Serialize to JSON
            serialized = json.dumps(value)
            await self._redis.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Redis SET error for key {key[:50]}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self._connected or not self._redis:
            return False

        try:
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key[:50]}: {e}")
            return False

    async def clear(self) -> bool:
        """
        Clear only LLM cache keys (not entire database).

        🔒 SECURITY: Uses pattern-based deletion instead of FLUSHDB
        to avoid wiping token revocations, rate limits, etc.

        Namespace: "llm_cache:*"
        """
        if not self._connected or not self._redis:
            return False

        try:
            pattern = "llm_cache:*"
            cursor = 0
            deleted = 0

            # Use SCAN to iterate keys without blocking Redis
            while True:
                cursor, keys = await self._redis.scan(
                    cursor,
                    match=pattern,
                    count=100  # Process 100 keys at a time
                )

                if keys:
                    deleted += await self._redis.delete(*keys)

                if cursor == 0:  # Scan complete
                    break

            logger.info(f"Cleared {deleted} LLM cache keys (pattern: {pattern})")
            return True

        except Exception as e:
            logger.error(f"Redis cache clear error: {e}")
            return False

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Awaitable[Any]],
        ttl: Optional[int] = None,
    ) -> Any:
        """
        Get value from cache or compute it with stampede protection.

        Uses Redis distributed locks to ensure only one request computes
        the value, while other concurrent requests wait for the result.

        Args:
            key: Cache key
            compute_fn: Async function to compute value on cache miss
            ttl: Optional TTL override

        Returns:
            Cached or computed value
        """
        if not self._connected or not self._redis:
            logger.warning("Redis not connected, computing without cache")
            return await compute_fn()

        # Fast path: check cache first (no lock needed)
        cached_value = await self.get(key)
        if cached_value is not None:
            logger.info(f"Cache HIT (no lock): {key[:50]}...")
            return cached_value

        # Cache miss - acquire lock to compute value
        lock_key = f"lock:{key}"
        lock = self._redis.lock(
            lock_key,
            timeout=self.lock_timeout,
            blocking_timeout=self.lock_blocking_timeout,
        )

        try:
            # Try to acquire lock
            acquired = await lock.acquire(blocking=True)

            if not acquired:
                # Timeout waiting for lock - compute anyway (degraded mode)
                logger.warning(f"Lock timeout for {key[:50]}, computing anyway")
                return await compute_fn()

            # Double-check cache after acquiring lock
            # (another request might have filled it while we waited)
            cached_value = await self.get(key)
            if cached_value is not None:
                logger.info(f"Cache HIT (after lock): {key[:50]}...")
                return cached_value

            # Still a miss - we get to compute
            logger.info(f"Cache MISS (locked): {key[:50]}...")
            result = await compute_fn()

            # Store result in cache
            await self.set(key, result, ttl)
            logger.info(f"Cached result for: {key[:50]}...")

            return result

        except asyncio.TimeoutError:
            logger.warning(f"Lock acquisition timeout for {key[:50]}")
            result = await compute_fn()
            try:
                await self.set(key, result, ttl)
                logger.info(f"Cached result (after lock timeout): {key[:50]}...")
            except Exception as cache_err:
                logger.warning(f"Failed to cache result for {key[:50]}: {cache_err}")
            return result

        except Exception as e:
            logger.error(f"Error in get_or_compute for {key[:50]}: {e}")
            # Retry compute and cache the result if retry succeeds
            result = await compute_fn()
            try:
                await self.set(key, result, ttl)
                logger.info(f"Cached retry result: {key[:50]}...")
            except Exception as cache_err:
                logger.warning(f"Failed to cache retry result for {key[:50]}: {cache_err}")
            return result

        finally:
            # Always release lock
            try:
                if await lock.owned():
                    await lock.release()
            except Exception as e:
                logger.error(f"Error releasing lock for {key[:50]}: {e}")
