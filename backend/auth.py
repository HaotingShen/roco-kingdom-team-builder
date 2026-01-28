"""Authentication utilities for JWT and password handling."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import bcrypt
from backend.config import (
    SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    COOKIE_SAMESITE
)


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Bcrypt automatically:
    - Generates a random salt
    - Uses slow hashing (prevents brute force)
    - Produces format: $2b$12$[salt][hash]
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its bcrypt hash.

    Uses constant-time comparison to prevent timing attacks.
    """
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(
    user_id: int,
    username: str,
    is_guest: bool,
    token_version: int = 0
) -> str:
    """
    Create a JWT access token (15 minutes).

    Payload includes:
    - sub: User ID
    - username: For display
    - is_guest: User type flag
    - token_version: For revocation
    - type: 'access' (vs 'refresh')
    - exp: Expiration timestamp
    - iat: Issued at timestamp
    - jti: JWT ID (for blacklist tracking)
    - csrf_token: Only if SameSite=None (cross-site)

    Returns:
        Encoded JWT token string
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "username": username,
        "is_guest": is_guest,
        "token_version": token_version,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_urlsafe(16),  # JWT ID for blacklist
    }

    # Add CSRF token for cross-site deployments
    if COOKIE_SAMESITE == "none":
        payload["csrf_token"] = secrets.token_urlsafe(16)

    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int, token_version: int = 0) -> str:
    """
    Create a JWT refresh token (7 days).

    SECURITY: This token will be stored in httpOnly cookie ONLY.
    Never send this in response body or store in localStorage.

    Payload includes:
    - sub: User ID
    - token_version: For revocation
    - type: 'refresh' (vs 'access')
    - exp: Expiration timestamp
    - iat: Issued at timestamp
    - jti: JWT ID (for blacklist tracking)

    Returns:
        Encoded JWT token string
    """
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "token_version": token_version,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Raises:
        jwt.ExpiredSignatureError: Token has expired
        jwt.InvalidTokenError: Token is invalid (signature, format)

    Returns:
        Decoded token payload dict
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])


def generate_guest_username() -> str:
    """
    Generate a unique guest username.

    Format: guest_{12_hex_chars}
    Example: guest_a1b2c3d4e5f6

    Used when device_id not provided (backward compatibility).
    """
    return f"guest_{uuid.uuid4().hex[:12]}"


# Characters for guest display ID (excluding confusables: 0/O, 1/I/L)
GUEST_DISPLAY_ID_CHARS = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'


def generate_guest_display_id() -> str:
    """
    Generate a random 4-character display ID for guests.

    Format: 4 alphanumeric chars (excluding confusables)
    Example: "A2B3", "X9Y8", "KMNP"

    Character set excludes 0/O, 1/I/L to avoid confusion.
    Total combinations: 30^4 = 810,000
    """
    return ''.join(secrets.choice(GUEST_DISPLAY_ID_CHARS) for _ in range(4))


def generate_verification_token() -> str:
    """
    Generate a secure email verification token.

    Uses 32-byte random URL-safe string (43 chars base64).
    Example: Xg3K9vZ2nR8tY1pL4mN7wQ5jH6fD8aB2cE0sT9xU3vA

    For Phase 7A email verification.
    """
    return secrets.token_urlsafe(32)
