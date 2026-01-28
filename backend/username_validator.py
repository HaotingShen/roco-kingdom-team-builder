"""
Username validation with Chinese character support.

Requirements:
- Allowed: Latin letters (A-Z a-z), digits (0-9), Chinese Han characters, underscore, hyphen
- Disallowed: spaces, emoji, symbols, punctuation (except _/-), control chars, zero-width chars
- Length: 2-16 graphemes (user-perceived characters)
- Security: Prevent confusable/look-alike characters for impersonation

Clean name rules:
- Trim whitespace (including full-width) before validation
- Cannot start or end with separators (_ or -)
- No consecutive separators (__, --, _-, -_)
- Must contain at least one letter or Chinese character (not digits-only)

Unicode ranges:
- CJK Unified Ideographs: U+4E00-U+9FFF (common Chinese)
- CJK Extension A: U+3400-U+4DBF (rare characters)
- CJK Extension B-G: U+20000-U+323AF (very rare, omitted for security)
"""

import re
import unicodedata
from typing import Optional, Tuple


# Allowed character pattern:
# - ASCII letters: a-zA-Z
# - Digits: 0-9
# - Underscore and hyphen: _-
# - CJK Unified Ideographs: \u4e00-\u9fff
# - CJK Extension A: \u3400-\u4dbf
ALLOWED_CHARS_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fff\u3400-\u4dbf]+$')

# Separator patterns for clean name validation
SEPARATORS = '_-'
CONSECUTIVE_SEPARATORS_PATTERN = re.compile(r'[_-]{2,}')  # Two or more separators in a row

# Pattern to check if username contains at least one letter (Latin or Chinese)
HAS_LETTER_PATTERN = re.compile(r'[a-zA-Z\u4e00-\u9fff\u3400-\u4dbf]')

# Whitespace characters to trim (including full-width space)
TRIM_CHARS = ' \t\n\r\u00A0\u3000\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A'

# Disallowed patterns (checked separately for better error messages)
SPACES_PATTERN = re.compile(r'[\s\u00A0\u3000\u2002-\u200B]')  # Various space chars including full-width
CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x1f\x7f-\x9f]')  # ASCII and Latin-1 control chars
ZERO_WIDTH_PATTERN = re.compile(r'[\u200B-\u200F\u2028-\u202F\uFEFF\u2060-\u206F]')  # Zero-width and format chars
EMOJI_PATTERN = re.compile(
    r'[\U0001F600-\U0001F64F'  # Emoticons
    r'\U0001F300-\U0001F5FF'  # Misc symbols and pictographs
    r'\U0001F680-\U0001F6FF'  # Transport and map
    r'\U0001F700-\U0001F77F'  # Alchemical symbols
    r'\U0001F780-\U0001F7FF'  # Geometric shapes extended
    r'\U0001F800-\U0001F8FF'  # Supplemental arrows
    r'\U0001F900-\U0001F9FF'  # Supplemental symbols
    r'\U0001FA00-\U0001FA6F'  # Chess symbols
    r'\U0001FA70-\U0001FAFF'  # Symbols and pictographs extended
    r'\U00002702-\U000027B0'  # Dingbats
    r'\U0001F1E0-\U0001F1FF'  # Flags
    r']'
)

# Confusable character mappings (common look-alikes)
# Maps confusable characters to their ASCII equivalents for comparison
CONFUSABLES = {
    # Cyrillic look-alikes for Latin
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'х': 'x',
    'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H',
    'О': 'O', 'Р': 'P', 'С': 'C', 'Т': 'T', 'Х': 'X',
    # Greek look-alikes
    'α': 'a', 'ο': 'o', 'ρ': 'p',
    'Α': 'A', 'Β': 'B', 'Ε': 'E', 'Η': 'H', 'Ι': 'I', 'Κ': 'K',
    'Μ': 'M', 'Ν': 'N', 'Ο': 'O', 'Ρ': 'P', 'Τ': 'T', 'Χ': 'X', 'Υ': 'Y',
    # Full-width Latin
    'Ａ': 'A', 'Ｂ': 'B', 'Ｃ': 'C', 'Ｄ': 'D', 'Ｅ': 'E', 'Ｆ': 'F',
    'Ｇ': 'G', 'Ｈ': 'H', 'Ｉ': 'I', 'Ｊ': 'J', 'Ｋ': 'K', 'Ｌ': 'L',
    'Ｍ': 'M', 'Ｎ': 'N', 'Ｏ': 'O', 'Ｐ': 'P', 'Ｑ': 'Q', 'Ｒ': 'R',
    'Ｓ': 'S', 'Ｔ': 'T', 'Ｕ': 'U', 'Ｖ': 'V', 'Ｗ': 'W', 'Ｘ': 'X',
    'Ｙ': 'Y', 'Ｚ': 'Z',
    'ａ': 'a', 'ｂ': 'b', 'ｃ': 'c', 'ｄ': 'd', 'ｅ': 'e', 'ｆ': 'f',
    'ｇ': 'g', 'ｈ': 'h', 'ｉ': 'i', 'ｊ': 'j', 'ｋ': 'k', 'ｌ': 'l',
    'ｍ': 'm', 'ｎ': 'n', 'ｏ': 'o', 'ｐ': 'p', 'ｑ': 'q', 'ｒ': 'r',
    'ｓ': 's', 'ｔ': 't', 'ｕ': 'u', 'ｖ': 'v', 'ｗ': 'w', 'ｘ': 'x',
    'ｙ': 'y', 'ｚ': 'z',
    # Full-width digits
    '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
    '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
    # Common substitutions
    'ı': 'i', 'ł': 'l', 'ß': 'ss',
    # Modifier letters
    'ᵃ': 'a', 'ᵇ': 'b', 'ᶜ': 'c', 'ᵈ': 'd', 'ᵉ': 'e',
}

# Reserved usernames (case-insensitive)
RESERVED_USERNAMES = {
    'admin', 'administrator', 'root', 'system', 'api', 'www',
    'null', 'undefined', 'guest', 'anonymous', 'support', 'help',
    'moderator', 'mod', 'official', 'staff', 'team',
}

# Grapheme counting using regex with \X (grapheme cluster)
# This handles combining characters, emoji sequences, etc.
try:
    import regex
    def count_graphemes(s: str) -> int:
        """Count user-perceived characters (grapheme clusters)."""
        return len(regex.findall(r'\X', s))
except ImportError:
    # Fallback: use unicodedata NFC normalization + simple len
    # This is less accurate for complex emoji but works for CJK + Latin
    def count_graphemes(s: str) -> int:
        """Count user-perceived characters (approximation)."""
        normalized = unicodedata.normalize('NFC', s)
        return len(normalized)


def normalize_username(username: str) -> str:
    """
    Normalize username for storage and comparison.

    - Apply Unicode NFC normalization
    - Convert confusable characters to their base form
    - Lowercase for case-insensitive comparison
    """
    # NFC normalization (compose combining characters)
    normalized = unicodedata.normalize('NFC', username)

    # Replace confusable characters
    result = []
    for char in normalized:
        if char in CONFUSABLES:
            result.append(CONFUSABLES[char])
        else:
            result.append(char)

    return ''.join(result).lower()


def trim_username(username: str) -> str:
    """
    Trim whitespace from username, including full-width spaces.
    """
    return username.strip(TRIM_CHARS)


def validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a username according to the requirements.

    Returns:
        (True, None) if valid
        (False, error_message) if invalid
    """
    if not username:
        return False, "Username cannot be empty"

    # Trim whitespace (including full-width spaces)
    trimmed = trim_username(username)
    if not trimmed:
        return False, "Username cannot be empty"

    # Normalize for validation
    normalized = unicodedata.normalize('NFC', trimmed)

    # Check for control characters
    if CONTROL_CHARS_PATTERN.search(normalized):
        return False, "Username contains invalid control characters"

    # Check for zero-width characters
    if ZERO_WIDTH_PATTERN.search(normalized):
        return False, "Username contains invisible characters"

    # Check for spaces (after trimming, internal spaces)
    if SPACES_PATTERN.search(normalized):
        return False, "Username cannot contain spaces"

    # Check for emoji
    if EMOJI_PATTERN.search(normalized):
        return False, "Username cannot contain emoji"

    # Check allowed character set
    if not ALLOWED_CHARS_PATTERN.match(normalized):
        return False, "Username can only contain letters, numbers, Chinese characters, underscores, and hyphens"

    # Check leading/trailing separators
    if normalized[0] in SEPARATORS:
        return False, "Username cannot start with an underscore or hyphen"
    if normalized[-1] in SEPARATORS:
        return False, "Username cannot end with an underscore or hyphen"

    # Check consecutive separators
    if CONSECUTIVE_SEPARATORS_PATTERN.search(normalized):
        return False, "Username cannot contain consecutive underscores or hyphens"

    # Check for digits-only (must have at least one letter)
    if not HAS_LETTER_PATTERN.search(normalized):
        return False, "Username must contain at least one letter"

    # Check grapheme length
    length = count_graphemes(normalized)
    if length < 2:
        return False, "Username must be at least 2 characters"
    if length > 16:
        return False, "Username cannot exceed 16 characters"

    # Check for confusable characters (security)
    for char in normalized:
        if char in CONFUSABLES:
            return False, f"Username contains a character that looks like another ('{char}'). Please use standard characters"

    # Check reserved usernames
    normalized_lower = normalize_username(trimmed)
    if normalized_lower in RESERVED_USERNAMES:
        return False, "This username is reserved"

    # Check guest_ prefix
    if normalized_lower.startswith('guest_') or normalized_lower.startswith('guest-'):
        return False, "Usernames cannot start with 'guest'"

    return True, None


def get_canonical_username(username: str) -> str:
    """
    Get the canonical form of a username for uniqueness checking.

    This normalizes confusables so that "аdmin" (Cyrillic а) and "admin"
    are considered the same username.
    """
    return normalize_username(username)
