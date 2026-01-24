"""CAPTCHA verification module for bot protection.

Supports:
- hCaptcha (recommended, privacy-focused)
- Google reCAPTCHA v2/v3

Enable in .env:
    CAPTCHA_ENABLED=true
    CAPTCHA_PROVIDER=hcaptcha
    CAPTCHA_SECRET_KEY=your-secret-key
    CAPTCHA_SITE_KEY=your-site-key
"""

import httpx
from typing import Optional
from fastapi import HTTPException, status
from backend.config import CAPTCHA_ENABLED, CAPTCHA_PROVIDER, CAPTCHA_SECRET_KEY, CAPTCHA_SITE_KEY
from backend.logger import logger

# Verification URLs for each provider
VERIFY_URLS = {
    "hcaptcha": "https://hcaptcha.com/siteverify",
    "recaptcha": "https://www.google.com/recaptcha/api/siteverify"
}


async def verify_captcha(token: Optional[str], remote_ip: Optional[str] = None) -> bool:
    """
    Verify CAPTCHA token with provider's API.

    Args:
        token: CAPTCHA response token from frontend
        remote_ip: Optional client IP for additional validation

    Returns:
        True if verification succeeded

    Raises:
        HTTPException 400: If CAPTCHA verification fails
    """
    # Skip if CAPTCHA is disabled
    if not CAPTCHA_ENABLED:
        return True

    # Token required when CAPTCHA is enabled
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CAPTCHA verification required"
        )

    verify_url = VERIFY_URLS.get(CAPTCHA_PROVIDER)
    if not verify_url:
        logger.error(f"Unknown CAPTCHA provider: {CAPTCHA_PROVIDER}")
        # Fail open in case of misconfiguration (log and allow)
        return True

    # Build request data
    data = {
        "secret": CAPTCHA_SECRET_KEY,
        "response": token
    }

    # Add remote IP if available (optional but recommended)
    if remote_ip:
        if CAPTCHA_PROVIDER == "hcaptcha":
            data["remoteip"] = remote_ip
        else:  # recaptcha
            data["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(verify_url, data=data)
            result = response.json()

        # Check verification result
        if result.get("success"):
            logger.debug(f"CAPTCHA verified successfully")
            return True
        else:
            error_codes = result.get("error-codes", [])
            logger.warning(f"CAPTCHA verification failed: {error_codes}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CAPTCHA verification failed. Please try again."
            )

    except httpx.RequestError as e:
        logger.error(f"CAPTCHA verification request failed: {e}")
        # Fail open on network errors (prevent blocking users due to CAPTCHA service issues)
        # In high-security scenarios, you might want to fail closed instead
        return True


def captcha_required() -> bool:
    """Check if CAPTCHA is enabled and required."""
    return CAPTCHA_ENABLED


def get_captcha_config() -> dict:
    """Get CAPTCHA configuration for frontend."""
    return {
        "enabled": CAPTCHA_ENABLED,
        "provider": CAPTCHA_PROVIDER if CAPTCHA_ENABLED else None,
        "siteKey": CAPTCHA_SITE_KEY if CAPTCHA_ENABLED else None
    }
