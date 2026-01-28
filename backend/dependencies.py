"""FastAPI dependency injection for authentication."""

from typing import Optional, Tuple
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import jwt
from backend.database import get_db
from backend import models
from backend.auth import decode_token
from backend.config import COOKIE_SAMESITE
from backend.logger import logger

# HTTP Bearer token scheme for Authorization header
security = HTTPBearer(auto_error=False)

# Constants
DEVICE_ID_HEADER = "X-Device-ID"
DEFAULT_DEVICE_ID = "unknown-device"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    """
    Get current authenticated user from JWT access token.

    SECURITY: Validates:
    - Token exists in Authorization header
    - Token is valid JWT
    - Token type is 'access' (not 'refresh')
    - User exists and is active
    - Token version matches user's current version (revocation check)
    - CSRF token matches (if SameSite=None)

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found
        HTTPException 403: If user is inactive

    Returns:
        User object from database
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = decode_token(token)

        # Verify token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        user_id = int(payload.get("sub"))
        token_version = payload.get("token_version", 0)

        # CSRF validation for cross-site deployments
        if COOKIE_SAMESITE == "none":
            csrf_header = request.headers.get("X-CSRF-Token")
            csrf_token = payload.get("csrf_token")
            if not csrf_header or csrf_header != csrf_token:
                logger.warning(f"CSRF validation failed for user {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="CSRF validation failed",
                )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # SECURITY: Check token version (invalidates all tokens if version changed)
    if token_version != user.token_version:
        logger.warning(
            f"Token version mismatch for user {user.id}: "
            f"token={token_version}, user={user.token_version}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    return user


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[models.User]:
    """
    Get current user if authenticated, None otherwise.

    Useful for endpoints that work for both authenticated and anonymous users.
    Does not raise exceptions on auth failure.

    Returns:
        User object if authenticated, None otherwise
    """
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        return None


async def require_registered_user(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """
    Ensure current user is NOT a guest (i.e., registered user).

    Use this for endpoints that require a registered account
    (e.g., accessing premium features).

    Raises:
        HTTPException 403: If user is a guest

    Returns:
        User object (guaranteed to be registered)
    """
    if current_user.is_guest:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a registered account. Please create an account to continue.",
        )

    return current_user


async def require_verified_email(
    current_user: models.User = Depends(require_registered_user)
) -> models.User:
    """
    Ensure current user has verified their email.

    SECURITY: Use this for sensitive operations (Phase 7A).

    Raises:
        HTTPException 403: If email not verified

    Returns:
        User object (guaranteed to have verified email)
    """
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires email verification. Please check your email for the verification link.",
        )

    return current_user


def get_user_team(
    team_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> models.Team:
    """
    Get a team and verify ownership.

    SECURITY: Prevents cross-user access to teams.

    This is a convenience dependency that combines:
    1. Fetching the team by ID
    2. Checking ownership (team.owner_id == current_user.id)

    Use this for GET/PUT/DELETE /teams/{id} endpoints.

    Raises:
        HTTPException 404: Team not found
        HTTPException 403: User doesn't own team

    Returns:
        Team object (guaranteed to be owned by current_user)
    """
    team = db.query(models.Team).filter(models.Team.id == team_id).first()

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    if team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this team",
        )

    return team


def get_device_id(request: Request) -> str:
    """
    Extract device ID from httpOnly cookie (set by DeviceIDMiddleware).

    Priority:
    1. request.state.device_id (set by middleware from cookie)
    2. X-Device-ID header (legacy fallback, deprecated)
    3. Default device ID

    The cookie-based approach is preferred because:
    - httpOnly: Cannot be read/modified by JavaScript (XSS protection)
    - Server-controlled: Cannot be faked by client
    - Automatic: Sent with every request

    Returns:
        Device ID string (UUID format)
    """
    # Primary: Cookie-based (set by DeviceIDMiddleware)
    if hasattr(request.state, 'device_id') and request.state.device_id:
        return request.state.device_id

    # Legacy fallback: Header-based (deprecated, for migration)
    header_device_id = request.headers.get(DEVICE_ID_HEADER)
    if header_device_id:
        logger.debug(f"Using legacy X-Device-ID header (deprecated): {header_device_id[:12]}...")
        return header_device_id

    return DEFAULT_DEVICE_ID


async def get_user_or_anonymous(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Tuple[Optional[models.User], str, str]:
    """
    Get current user if authenticated, or anonymous context.

    For the three-tier system:
    - Anonymous: No user (user=None), tracked by device_id + IP
    - Guest: user.is_guest=True, subscription_tier="guest"
    - Registered: user.is_guest=False, subscription_tier="free" or higher

    Returns:
        Tuple of (user, device_id, client_ip):
        - user: User object if authenticated, None for anonymous
        - device_id: From httpOnly cookie (for tracking and daily caps)
        - client_ip: Client IP address (for tracking and fallback caps)
    """
    from backend.rate_limiter import get_real_client_ip

    # Extract device_id and IP regardless of auth status
    device_id = get_device_id(request)
    client_ip = get_real_client_ip(request)

    # Try to get authenticated user
    user = await get_optional_user(request, credentials, db)

    return (user, device_id, client_ip)


# ========== ADMIN DEPENDENCIES (Phase B) ==========

def is_admin_email(email: Optional[str]) -> bool:
    """
    Check if an email address belongs to an admin.

    Admin emails are defined in the ADMIN_EMAILS environment variable.
    This approach keeps admin privileges environment-controlled
    (more secure than database flags - can't be SQL injected).

    Args:
        email: Email address to check (can be None for guests)

    Returns:
        True if email is in admin list, False otherwise
    """
    from backend.config import ADMIN_EMAILS

    if not email:
        return False
    return email.lower() in ADMIN_EMAILS


def is_admin_user(user: models.User) -> bool:
    """
    Check if a user has admin privileges.

    Args:
        user: User model instance

    Returns:
        True if user is an admin, False otherwise
    """
    return is_admin_email(user.email)


async def require_admin(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """
    Dependency that requires admin privileges.

    SECURITY:
    - User must be authenticated
    - User must have email in ADMIN_EMAILS list
    - User must NOT be a guest (guests have no email)

    Use this for all admin endpoints.

    Raises:
        HTTPException 403: If user is not an admin

    Returns:
        User object (guaranteed to be admin)
    """
    if current_user.is_guest:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. Guest accounts cannot be admins.",
        )

    if not is_admin_user(current_user):
        logger.warning(
            f"Admin access denied for user {current_user.id} ({current_user.email})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )

    return current_user
