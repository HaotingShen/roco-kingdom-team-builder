"""Token revocation service using Redis blacklist."""

from typing import Optional
from redis import asyncio as redis
from backend.config import (
    REDIS_URL,
    REFRESH_TOKEN_EXPIRE_DAYS,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from backend.logger import logger


class TokenRevocationService:
    """
    SECURITY: Token revocation using Redis blacklist.

    Strategy:
    - Blacklist tokens by JTI (JWT ID) when user logs out
    - Redis TTL automatically expires entries after token expiry
    - Namespace: "revoked_token:"

    Single-Instance Architecture:
    - Redis runs on same EC2 as FastAPI (localhost connection)
    - Fast, no network latency
    - Shared memory space efficient
    """

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        """Establish Redis connection (localhost for single-instance)."""
        if self._redis is None:
            self._redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("Token revocation service connected to Redis")

    async def disconnect(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def revoke_token(self, jti: str, token_type: str = "refresh"):
        """
        Blacklist a token by its JTI (JWT ID).

        CRITICAL: Always uses SETEX (SET + EXPIRE in one atomic operation)
        to prevent memory leaks. Never use SET without TTL!

        Args:
            jti: JWT ID from token payload
            token_type: 'access' or 'refresh' (affects TTL)
        """
        if not self._redis:
            await self.connect()

        # Calculate TTL based on token type
        ttl_seconds = (
            REFRESH_TOKEN_EXPIRE_DAYS * 86400
            if token_type == "refresh"
            else ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

        key = f"revoked_token:{jti}"

        # Use SETEX (atomic SET + EXPIRE)
        await self._redis.setex(key, ttl_seconds, "revoked")

        # Paranoid check: Verify TTL was set
        actual_ttl = await self._redis.ttl(key)
        if actual_ttl == -1:  # -1 = no expiration (ERROR!)
            logger.error(
                f"CRITICAL: Redis key {key} has no TTL! "
                f"This is a memory leak. Manually setting TTL."
            )
            await self._redis.expire(key, ttl_seconds)

        logger.info(f"Revoked {token_type} token: {jti} (TTL={ttl_seconds}s)")

    async def is_token_revoked(self, jti: str) -> bool:
        """
        Check if a token has been revoked.

        Args:
            jti: JWT ID from token payload

        Returns:
            True if token is blacklisted, False otherwise
        """
        if not self._redis:
            await self.connect()

        key = f"revoked_token:{jti}"
        result = await self._redis.exists(key)
        return bool(result)

    async def revoke_all_user_tokens(self, user_id: int):
        """
        Revoke all tokens for a user.

        SECURITY: Use this on password change, account compromise, etc.

        Note: This increments user.token_version in the database.
        The token version check in get_current_user() will reject old tokens.

        We don't actually add all tokens to blacklist - we just bump the version.
        """
        logger.info(
            f"Revoking all tokens for user {user_id} via token_version increment"
        )
        # The actual token_version increment happens in the endpoint
        # (see /auth/logout-all)


# Global instance
revocation_service = TokenRevocationService(REDIS_URL)
