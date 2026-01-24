"""
Email service for transactional emails.

Supports:
- Email verification
- Password reset
- Email change confirmation

Uses aiosmtplib for async SMTP to avoid blocking the event loop.
Falls back to logging if SMTP is not configured (development mode).
"""

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from backend.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    SMTP_FROM_EMAIL, SMTP_FROM_NAME, SMTP_USE_TLS,
    FRONTEND_URL, ENVIRONMENT
)
from backend.logger import logger


def is_smtp_configured() -> bool:
    """Check if SMTP is properly configured."""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


async def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """
    Send email via SMTP (async).

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_body: HTML content of the email
        text_body: Plain text fallback (optional)

    Returns:
        True if sent successfully, False otherwise.
        Falls back to logging if SMTP is not configured.
    """
    if not is_smtp_configured():
        # Development mode: Log email instead of sending
        logger.warning(
            f"[EMAIL-DEV] SMTP not configured. Email would be sent:\n"
            f"  To: {to_email}\n"
            f"  Subject: {subject}\n"
            f"  HTML Body:\n{html_body[:500]}..."
        )
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg['To'] = to_email

    # Add plain text version (for email clients that don't support HTML)
    if text_body:
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        if SMTP_USE_TLS:
            # STARTTLS on port 587 (most common)
            await aiosmtplib.send(
                msg,
                hostname=SMTP_HOST,
                port=SMTP_PORT,
                username=SMTP_USER,
                password=SMTP_PASSWORD,
                start_tls=True
            )
        else:
            # Direct SSL on port 465
            await aiosmtplib.send(
                msg,
                hostname=SMTP_HOST,
                port=SMTP_PORT,
                username=SMTP_USER,
                password=SMTP_PASSWORD,
                use_tls=True
            )

        logger.info(f"Email sent to {to_email}: {subject}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


async def send_verification_email(to_email: str, token: str) -> bool:
    """
    Send email verification email.

    Args:
        to_email: Recipient email address
        token: Verification token

    Returns:
        True if sent successfully
    """
    verify_url = f"{FRONTEND_URL}/auth/verify?token={token}"

    subject = "Verify your email - Roco Kingdom Team Builder"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333;">Verify Your Email</h2>
        <p>Thank you for registering! Please click the link below to verify your email address:</p>
        <p style="margin: 20px 0;">
            <a href="{verify_url}"
               style="background-color: #2563eb; color: white; padding: 12px 24px;
                      text-decoration: none; border-radius: 6px; display: inline-block;">
                Verify Email
            </a>
        </p>
        <p style="color: #666; font-size: 14px;">
            Or copy and paste this link into your browser:<br>
            <a href="{verify_url}" style="color: #2563eb;">{verify_url}</a>
        </p>
        <p style="color: #666; font-size: 14px;">This link expires in 24 hours.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #999; font-size: 12px;">
            If you didn't create an account, you can safely ignore this email.
        </p>
    </body>
    </html>
    """
    text_body = f"Verify your email: {verify_url}\n\nThis link expires in 24 hours."

    return await send_email(to_email, subject, html_body, text_body)


async def send_password_reset_email(to_email: str, token: str) -> bool:
    """
    Send password reset email.

    Args:
        to_email: Recipient email address
        token: Password reset token

    Returns:
        True if sent successfully
    """
    reset_url = f"{FRONTEND_URL}/auth/reset-password?token={token}"

    subject = "Reset your password - Roco Kingdom Team Builder"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333;">Reset Your Password</h2>
        <p>We received a request to reset your password. Click the link below to create a new password:</p>
        <p style="margin: 20px 0;">
            <a href="{reset_url}"
               style="background-color: #2563eb; color: white; padding: 12px 24px;
                      text-decoration: none; border-radius: 6px; display: inline-block;">
                Reset Password
            </a>
        </p>
        <p style="color: #666; font-size: 14px;">
            Or copy and paste this link into your browser:<br>
            <a href="{reset_url}" style="color: #2563eb;">{reset_url}</a>
        </p>
        <p style="color: #666; font-size: 14px;"><strong>This link expires in 1 hour.</strong></p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #999; font-size: 12px;">
            If you didn't request a password reset, you can safely ignore this email.
            Your password will remain unchanged.
        </p>
    </body>
    </html>
    """
    text_body = f"Reset your password: {reset_url}\n\nThis link expires in 1 hour."

    return await send_email(to_email, subject, html_body, text_body)


async def send_email_change_verification(to_email: str, token: str) -> bool:
    """
    Send email change verification to the NEW email address.

    Args:
        to_email: New email address to verify
        token: Email change token

    Returns:
        True if sent successfully
    """
    verify_url = f"{FRONTEND_URL}/auth/confirm-email?token={token}"

    subject = "Confirm your new email - Roco Kingdom Team Builder"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333;">Confirm Your New Email</h2>
        <p>You requested to change your email address. Click the link below to confirm:</p>
        <p style="margin: 20px 0;">
            <a href="{verify_url}"
               style="background-color: #2563eb; color: white; padding: 12px 24px;
                      text-decoration: none; border-radius: 6px; display: inline-block;">
                Confirm Email Change
            </a>
        </p>
        <p style="color: #666; font-size: 14px;">
            Or copy and paste this link into your browser:<br>
            <a href="{verify_url}" style="color: #2563eb;">{verify_url}</a>
        </p>
        <p style="color: #666; font-size: 14px;">This link expires in 24 hours.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #999; font-size: 12px;">
            If you didn't request this change, please ignore this email and your email will remain unchanged.
        </p>
    </body>
    </html>
    """
    text_body = f"Confirm your new email: {verify_url}\n\nThis link expires in 24 hours."

    return await send_email(to_email, subject, html_body, text_body)
