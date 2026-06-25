from email.message import EmailMessage

import aiosmtplib

from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USERNAME and settings.SMTP_PASSWORD)


async def send_email(to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    if not _smtp_configured():
        logger.info(
            "SMTP not configured — email simulated to %s | Subject: %s\n%s",
            to_email,
            subject,
            body_text,
        )
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_USE_TLS,
        )
        logger.info("Email dispatched to %s — %s", to_email, subject)
        return True
    except Exception as exc:
        logger.error("SMTP dispatch failed for %s: %s", to_email, exc, exc_info=True)
        return False


async def send_password_reset_email(to_email: str, reset_token: str, full_name: str) -> bool:
    reset_url = f"{settings.APP_BASE_URL.rstrip('/')}/reset-password?token={reset_token}"
    subject = "NexusAI — Password Reset Request"
    body_text = (
        f"Hello {full_name},\n\n"
        f"We received a password reset request for your NexusAI account.\n"
        f"Reset your password using this link (expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes):\n\n"
        f"{reset_url}\n\n"
        f"If you did not request this, ignore this email.\n\n"
        f"— NexusAI Security Team"
    )
    body_html = f"""
    <html><body style="font-family:Inter,sans-serif;background:#0b0f19;color:#e2e8f0;padding:24px;">
    <div style="max-width:520px;margin:auto;background:#111827;border:1px solid #334155;border-radius:16px;padding:24px;">
    <h2 style="color:#818cf8;">NexusAI Password Reset</h2>
    <p>Hello {full_name},</p>
    <p>Click the button below to reset your password. This link expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes.</p>
    <p><a href="{reset_url}" style="display:inline-block;background:#6366f1;color:#fff;padding:12px 20px;border-radius:12px;text-decoration:none;font-weight:600;">Reset Password</a></p>
    <p style="font-size:12px;color:#94a3b8;">If you did not request this, you can safely ignore this email.</p>
    </div></body></html>
    """
    return await send_email(to_email, subject, body_text, body_html)
