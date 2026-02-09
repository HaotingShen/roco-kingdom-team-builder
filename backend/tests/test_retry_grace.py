"""
Tests for retry grace functions in tier_limits.py.

Retry grace allows free retries after partial analysis failure.
When an analysis partially succeeds (e.g., 6/7 LLM calls), quota is charged
immediately and a grace marker is set so the retry is truly free.
"""

import asyncio
import pytest
from unittest.mock import patch
from backend.tier_limits import (
    _get_retry_grace_key,
    _resolve_grace_identity,
    set_retry_grace,
    check_retry_grace,
    consume_retry_grace,
    clear_retry_grace,
)


def run(coro):
    """Helper to run async functions in synchronous tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ========== Fixtures ==========


class FakeUser:
    """Minimal user mock for testing."""
    def __init__(self, user_id: int):
        self.id = user_id


class FakeRedis:
    """In-memory Redis mock for testing grace functions."""
    def __init__(self):
        self._store = {}

    def setex(self, key, ttl, value):
        self._store[key] = str(value)

    def get(self, key):
        return self._store.get(key)

    def decr(self, key):
        if key not in self._store:
            self._store[key] = "-1"
            return -1
        self._store[key] = str(int(self._store[key]) - 1)
        return int(self._store[key])

    def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                count += 1
        return count

    def ping(self):
        return True


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def mock_redis(fake_redis):
    """Patch get_redis to return our fake Redis."""
    with patch("backend.tier_limits.get_redis", return_value=fake_redis):
        yield fake_redis


@pytest.fixture
def mock_redis_unavailable():
    """Patch get_redis to return None (Redis unavailable)."""
    with patch("backend.tier_limits.get_redis", return_value=None):
        yield


# ========== _get_retry_grace_key ==========


class TestGetRetryGraceKey:
    def test_user_key_format(self):
        key = _get_retry_grace_key("user", "42", "abc123", "zh")
        assert key == "retry_grace:user:42:abc123:zh"

    def test_device_key_format(self):
        key = _get_retry_grace_key("device", "dev-001", "hash456", "en")
        assert key == "retry_grace:device:dev-001:hash456:en"

    def test_ip_key_format(self):
        key = _get_retry_grace_key("ip", "127.0.0.1", "hash789", "zh")
        assert key == "retry_grace:ip:127.0.0.1:hash789:zh"

    def test_different_language_different_key(self):
        key_zh = _get_retry_grace_key("user", "1", "hash", "zh")
        key_en = _get_retry_grace_key("user", "1", "hash", "en")
        assert key_zh != key_en

    def test_different_team_hash_different_key(self):
        key_a = _get_retry_grace_key("user", "1", "hashA", "zh")
        key_b = _get_retry_grace_key("user", "1", "hashB", "zh")
        assert key_a != key_b


# ========== _resolve_grace_identity ==========


class TestResolveGraceIdentity:
    def test_authenticated_user_uses_user_id(self):
        user = FakeUser(42)
        identity_type, identity_value = _resolve_grace_identity(user, "dev-001", "1.2.3.4")
        assert identity_type == "user"
        assert identity_value == "42"

    def test_anonymous_with_device_uses_device(self):
        identity_type, identity_value = _resolve_grace_identity(None, "dev-001", "1.2.3.4")
        assert identity_type == "device"
        assert identity_value == "dev-001"

    def test_anonymous_unknown_device_uses_ip(self):
        identity_type, identity_value = _resolve_grace_identity(None, "unknown-device", "1.2.3.4")
        assert identity_type == "ip"
        assert identity_value == "1.2.3.4"

    def test_user_takes_priority_over_device(self):
        """Even if device_id is known, authenticated user ID is used."""
        user = FakeUser(99)
        identity_type, _ = _resolve_grace_identity(user, "dev-001", "1.2.3.4")
        assert identity_type == "user"

    def test_device_takes_priority_over_ip(self):
        """Known device takes priority over IP for anonymous users."""
        identity_type, _ = _resolve_grace_identity(None, "my-device", "1.2.3.4")
        assert identity_type == "device"


# ========== set_retry_grace ==========


class TestSetRetryGrace:
    def test_sets_key_for_authenticated_user(self, mock_redis):
        user = FakeUser(42)
        run(set_retry_grace(user, "dev-001", "1.2.3.4", "teamhash", "zh"))
        expected_key = "retry_grace:user:42:teamhash:zh"
        assert mock_redis.get(expected_key) == "3"  # default RETRY_GRACE_MAX_RETRIES

    def test_sets_key_for_anonymous_device(self, mock_redis):
        run(set_retry_grace(None, "dev-001", "1.2.3.4", "teamhash", "en"))
        expected_key = "retry_grace:device:dev-001:teamhash:en"
        assert mock_redis.get(expected_key) == "3"

    def test_sets_key_for_anonymous_unknown_device(self, mock_redis):
        run(set_retry_grace(None, "unknown-device", "1.2.3.4", "teamhash", "zh"))
        expected_key = "retry_grace:ip:1.2.3.4:teamhash:zh"
        assert mock_redis.get(expected_key) == "3"

    def test_only_sets_one_key(self, mock_redis):
        """Ensures only most-specific identity is used (no IP key for authenticated user)."""
        user = FakeUser(42)
        run(set_retry_grace(user, "dev-001", "1.2.3.4", "teamhash", "zh"))
        # User key should exist
        assert mock_redis.get("retry_grace:user:42:teamhash:zh") == "3"
        # Device and IP keys should NOT exist
        assert mock_redis.get("retry_grace:device:dev-001:teamhash:zh") is None
        assert mock_redis.get("retry_grace:ip:1.2.3.4:teamhash:zh") is None

    def test_redis_unavailable_no_error(self, mock_redis_unavailable):
        """Should not raise when Redis is unavailable."""
        run(set_retry_grace(FakeUser(1), "dev", "ip", "hash", "en"))


# ========== check_retry_grace ==========


class TestCheckRetryGrace:
    def test_returns_true_when_grace_exists(self, mock_redis):
        mock_redis.setex("retry_grace:user:42:hash:zh", 900, 3)
        result = run(check_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert result is True

    def test_returns_false_when_no_grace(self, mock_redis):
        result = run(check_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert result is False

    def test_returns_false_when_counter_is_zero(self, mock_redis):
        mock_redis.setex("retry_grace:user:42:hash:zh", 900, 0)
        result = run(check_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert result is False

    def test_redis_unavailable_returns_false(self, mock_redis_unavailable):
        result = run(check_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert result is False

    def test_different_language_no_match(self, mock_redis):
        mock_redis.setex("retry_grace:user:42:hash:zh", 900, 3)
        result = run(check_retry_grace(FakeUser(42), "dev", "ip", "hash", "en"))
        assert result is False

    def test_different_team_hash_no_match(self, mock_redis):
        mock_redis.setex("retry_grace:user:42:hashA:zh", 900, 3)
        result = run(check_retry_grace(FakeUser(42), "dev", "ip", "hashB", "zh"))
        assert result is False

    def test_uses_most_specific_identity(self, mock_redis):
        """If user is authenticated, checks user key, not device or IP."""
        # Set device key but not user key
        mock_redis.setex("retry_grace:device:dev:hash:zh", 900, 3)
        result = run(check_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert result is False  # User key doesn't exist


# ========== consume_retry_grace ==========


class TestConsumeRetryGrace:
    def test_decrements_counter(self, mock_redis):
        mock_redis.setex("retry_grace:user:42:hash:zh", 900, 3)
        result = run(consume_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert result is True
        assert mock_redis.get("retry_grace:user:42:hash:zh") == "2"

    def test_returns_false_when_exhausted(self, mock_redis):
        mock_redis.setex("retry_grace:user:42:hash:zh", 900, 1)
        result = run(consume_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert result is False  # Counter was 1, decremented to 0
        # Key should be deleted
        assert mock_redis.get("retry_grace:user:42:hash:zh") is None

    def test_returns_false_when_no_key(self, mock_redis):
        result = run(consume_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert result is False

    def test_multiple_consumes(self, mock_redis):
        mock_redis.setex("retry_grace:user:42:hash:zh", 900, 3)

        r1 = run(consume_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert r1 is True
        assert mock_redis.get("retry_grace:user:42:hash:zh") == "2"

        r2 = run(consume_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert r2 is True
        assert mock_redis.get("retry_grace:user:42:hash:zh") == "1"

        r3 = run(consume_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert r3 is False  # Decremented to 0, exhausted
        assert mock_redis.get("retry_grace:user:42:hash:zh") is None

    def test_redis_unavailable_returns_false(self, mock_redis_unavailable):
        result = run(consume_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert result is False


# ========== clear_retry_grace ==========


class TestClearRetryGrace:
    def test_deletes_key(self, mock_redis):
        mock_redis.setex("retry_grace:user:42:hash:zh", 900, 3)
        run(clear_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))
        assert mock_redis.get("retry_grace:user:42:hash:zh") is None

    def test_no_error_when_key_missing(self, mock_redis):
        """Should not raise when key doesn't exist."""
        run(clear_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))

    def test_redis_unavailable_no_error(self, mock_redis_unavailable):
        """Should not raise when Redis is unavailable."""
        run(clear_retry_grace(FakeUser(42), "dev", "ip", "hash", "zh"))


# ========== Integration-style: full lifecycle ==========


class TestRetryGraceLifecycle:
    def test_set_check_consume_clear(self, mock_redis):
        """Full lifecycle: set -> check -> consume -> consume -> consume -> exhausted."""
        user = FakeUser(1)
        team_hash = "abc123"
        lang = "zh"

        # Initially no grace
        assert run(check_retry_grace(user, "d", "ip", team_hash, lang)) is False

        # Set grace (partial failure)
        run(set_retry_grace(user, "d", "ip", team_hash, lang))
        assert run(check_retry_grace(user, "d", "ip", team_hash, lang)) is True

        # Consume retries (default max = 3)
        assert run(consume_retry_grace(user, "d", "ip", team_hash, lang)) is True  # 3->2
        assert run(consume_retry_grace(user, "d", "ip", team_hash, lang)) is True  # 2->1
        assert run(consume_retry_grace(user, "d", "ip", team_hash, lang)) is False  # 1->0, exhausted

        # Grace should be gone
        assert run(check_retry_grace(user, "d", "ip", team_hash, lang)) is False

    def test_set_then_clear_on_success(self, mock_redis):
        """Partial failure -> grace set -> retry succeeds -> grace cleared."""
        user = FakeUser(1)

        run(set_retry_grace(user, "d", "ip", "hash", "en"))
        assert run(check_retry_grace(user, "d", "ip", "hash", "en")) is True

        # Retry: consume one
        run(consume_retry_grace(user, "d", "ip", "hash", "en"))

        # Retry succeeded: clear grace
        run(clear_retry_grace(user, "d", "ip", "hash", "en"))
        assert run(check_retry_grace(user, "d", "ip", "hash", "en")) is False

    def test_different_team_independent(self, mock_redis):
        """Grace for team A does not affect team B."""
        user = FakeUser(1)

        run(set_retry_grace(user, "d", "ip", "teamA", "zh"))
        assert run(check_retry_grace(user, "d", "ip", "teamA", "zh")) is True
        assert run(check_retry_grace(user, "d", "ip", "teamB", "zh")) is False

    def test_different_language_independent(self, mock_redis):
        """Grace for zh does not affect en."""
        user = FakeUser(1)

        run(set_retry_grace(user, "d", "ip", "hash", "zh"))
        assert run(check_retry_grace(user, "d", "ip", "hash", "zh")) is True
        assert run(check_retry_grace(user, "d", "ip", "hash", "en")) is False
