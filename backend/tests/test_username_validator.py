"""Tests for username validation with Chinese character support."""

import pytest
from backend.username_validator import (
    validate_username,
    normalize_username,
    get_canonical_username,
    count_graphemes,
    trim_username,
)


class TestTrimUsername:
    """Test whitespace trimming."""

    def test_trim_leading_space(self):
        assert trim_username("  hello") == "hello"

    def test_trim_trailing_space(self):
        assert trim_username("hello  ") == "hello"

    def test_trim_both_sides(self):
        assert trim_username("  hello  ") == "hello"

    def test_trim_fullwidth_space(self):
        assert trim_username("\u3000hello\u3000") == "hello"

    def test_trim_mixed_whitespace(self):
        assert trim_username(" \t\n\u3000hello\u00A0 ") == "hello"

    def test_no_trim_needed(self):
        assert trim_username("hello") == "hello"


class TestCountGraphemes:
    """Test grapheme counting."""

    def test_ascii_letters(self):
        assert count_graphemes("hello") == 5

    def test_chinese_characters(self):
        assert count_graphemes("你好世界") == 4

    def test_mixed_ascii_chinese(self):
        assert count_graphemes("hello你好") == 7

    def test_emoji_as_single_grapheme(self):
        # Basic emoji should count as 1
        assert count_graphemes("👍") == 1

    def test_empty_string(self):
        assert count_graphemes("") == 0


class TestValidateUsername:
    """Test username validation rules."""

    # Valid usernames
    def test_valid_ascii_only(self):
        is_valid, error = validate_username("testuser")
        assert is_valid is True
        assert error is None

    def test_valid_with_numbers(self):
        is_valid, error = validate_username("user123")
        assert is_valid is True

    def test_valid_with_underscore(self):
        is_valid, error = validate_username("test_user")
        assert is_valid is True

    def test_valid_with_hyphen(self):
        is_valid, error = validate_username("test-user")
        assert is_valid is True

    def test_valid_chinese_only(self):
        is_valid, error = validate_username("测试用户")
        assert is_valid is True

    def test_valid_mixed_chinese_ascii(self):
        is_valid, error = validate_username("玩家Player1")
        assert is_valid is True

    def test_valid_minimum_length(self):
        is_valid, error = validate_username("ab")
        assert is_valid is True

    def test_valid_maximum_length(self):
        is_valid, error = validate_username("a" * 16)
        assert is_valid is True

    def test_valid_chinese_max_length(self):
        # 16 Chinese characters should be valid
        is_valid, error = validate_username("我" * 16)
        assert is_valid is True

    # Invalid: too short
    def test_invalid_too_short(self):
        is_valid, error = validate_username("a")
        assert is_valid is False
        assert "at least 2" in error

    def test_invalid_empty(self):
        is_valid, error = validate_username("")
        assert is_valid is False

    # Invalid: too long
    def test_invalid_too_long_ascii(self):
        is_valid, error = validate_username("a" * 17)
        assert is_valid is False
        assert "exceed 16" in error

    def test_invalid_too_long_chinese(self):
        is_valid, error = validate_username("我" * 17)
        assert is_valid is False
        assert "exceed 16" in error

    # Invalid: spaces
    def test_invalid_space(self):
        is_valid, error = validate_username("test user")
        assert is_valid is False
        assert "spaces" in error.lower()

    def test_invalid_fullwidth_space(self):
        is_valid, error = validate_username("test\u3000user")  # Full-width space
        assert is_valid is False
        assert "spaces" in error.lower()

    # Invalid: emoji
    def test_invalid_emoji(self):
        is_valid, error = validate_username("user👍")
        assert is_valid is False
        assert "emoji" in error.lower()

    # Invalid: control characters
    def test_invalid_control_char(self):
        is_valid, error = validate_username("user\x00name")
        assert is_valid is False
        assert "control" in error.lower()

    # Invalid: zero-width characters
    def test_invalid_zero_width(self):
        is_valid, error = validate_username("user\u200Bname")  # Zero-width space
        assert is_valid is False
        assert "invisible" in error.lower()

    # Invalid: special characters
    def test_invalid_at_symbol(self):
        is_valid, error = validate_username("user@name")
        assert is_valid is False

    def test_invalid_dot(self):
        is_valid, error = validate_username("user.name")
        assert is_valid is False

    # Invalid: confusable characters
    def test_invalid_cyrillic_a(self):
        # Cyrillic 'а' looks like Latin 'a' - rejected either as invalid char or confusable
        is_valid, error = validate_username("аdmin")  # First char is Cyrillic
        assert is_valid is False
        # May be rejected by allowed chars check or confusables check - both are correct
        assert error is not None

    def test_invalid_fullwidth_latin(self):
        is_valid, error = validate_username("Ａdmin")  # Full-width A
        assert is_valid is False

    # Reserved usernames
    def test_invalid_reserved_admin(self):
        is_valid, error = validate_username("admin")
        assert is_valid is False
        assert "reserved" in error.lower()

    def test_invalid_reserved_root(self):
        is_valid, error = validate_username("root")
        assert is_valid is False

    def test_invalid_reserved_system(self):
        is_valid, error = validate_username("System")  # Case insensitive
        assert is_valid is False

    def test_invalid_guest_prefix(self):
        is_valid, error = validate_username("guest_12345")
        assert is_valid is False
        assert "guest" in error.lower()

    # Clean name rules: leading/trailing separators
    def test_invalid_leading_underscore(self):
        is_valid, error = validate_username("_username")
        assert is_valid is False
        assert "start" in error.lower()

    def test_invalid_trailing_underscore(self):
        is_valid, error = validate_username("username_")
        assert is_valid is False
        assert "end" in error.lower()

    def test_invalid_leading_hyphen(self):
        is_valid, error = validate_username("-username")
        assert is_valid is False
        assert "start" in error.lower()

    def test_invalid_trailing_hyphen(self):
        is_valid, error = validate_username("username-")
        assert is_valid is False
        assert "end" in error.lower()

    # Clean name rules: consecutive separators
    def test_invalid_double_underscore(self):
        is_valid, error = validate_username("user__name")
        assert is_valid is False
        assert "consecutive" in error.lower()

    def test_invalid_double_hyphen(self):
        is_valid, error = validate_username("user--name")
        assert is_valid is False
        assert "consecutive" in error.lower()

    def test_invalid_mixed_separators(self):
        is_valid, error = validate_username("user_-name")
        assert is_valid is False
        assert "consecutive" in error.lower()

    def test_invalid_triple_separator(self):
        is_valid, error = validate_username("user___name")
        assert is_valid is False
        assert "consecutive" in error.lower()

    # Clean name rules: digits-only
    def test_invalid_digits_only(self):
        is_valid, error = validate_username("12345")
        assert is_valid is False
        assert "letter" in error.lower()

    def test_invalid_digits_with_separators(self):
        is_valid, error = validate_username("123_456")
        assert is_valid is False
        assert "letter" in error.lower()

    # Whitespace trimming
    def test_valid_after_trim(self):
        is_valid, error = validate_username("  username  ")
        assert is_valid is True

    def test_valid_after_fullwidth_trim(self):
        is_valid, error = validate_username("\u3000username\u3000")
        assert is_valid is True

    def test_invalid_only_whitespace(self):
        is_valid, error = validate_username("   ")
        assert is_valid is False
        assert "empty" in error.lower()


class TestNormalizeUsername:
    """Test username normalization for comparison."""

    def test_lowercase(self):
        assert normalize_username("TestUser") == "testuser"

    def test_confusable_replacement(self):
        # Cyrillic 'а' should be replaced with Latin 'a'
        result = normalize_username("аdmin")
        assert result == "admin"

    def test_fullwidth_replacement(self):
        result = normalize_username("Ａｄｍｉｎ")
        assert result == "admin"

    def test_chinese_preserved(self):
        # Chinese characters should remain unchanged
        result = normalize_username("测试User")
        assert "测试" in result
        assert "user" in result


class TestGetCanonicalUsername:
    """Test canonical username for uniqueness checking."""

    def test_same_canonical_for_confusables(self):
        # These should have the same canonical form
        assert get_canonical_username("admin") == get_canonical_username("аdmin")

    def test_case_insensitive(self):
        assert get_canonical_username("Admin") == get_canonical_username("admin")

    def test_fullwidth_normalized(self):
        assert get_canonical_username("Ａdmin") == get_canonical_username("admin")
