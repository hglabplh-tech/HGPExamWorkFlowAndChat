"""Audited SMTP notification delivery for scoring and question responses.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import asyncio
import smtplib
from email.message import EmailMessage

from ..config import get_settings


def _send(recipient: str, subject: str, body: str) -> None:
    """Send one plain-text message through the configured authenticated SMTP relay."""
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is not configured")
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


async def send_email(recipient: str, subject: str, body: str) -> None:
    """Move blocking SMTP I/O off the FastAPI event loop."""
    await asyncio.to_thread(_send, recipient, subject, body)
