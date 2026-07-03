"""Audited SMTP notification delivery for scoring and question responses.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import asyncio
import smtplib
from email.message import EmailMessage

from sqlalchemy import select

from ..config import get_settings
from ..database import SessionLocal
from ..models import MailServerSettings


async def _effective_mail_settings() -> dict:
    """Load administrator mail settings and fall back to environment values."""
    env = get_settings()
    values = {
        "smtp_host": env.smtp_host,
        "smtp_port": env.smtp_port,
        "smtp_username": env.smtp_username,
        "smtp_password": env.smtp_password.get_secret_value(),
        "smtp_starttls": env.smtp_starttls,
        "smtp_ssl": False,
        "email_from": env.email_from,
    }
    async with SessionLocal() as db:
        saved = await db.scalar(select(MailServerSettings).where(
            MailServerSettings.name == "default",
            MailServerSettings.active.is_(True),
        ))
        if saved:
            values.update({
                "smtp_host": saved.smtp_host or values["smtp_host"],
                "smtp_port": saved.smtp_port,
                "smtp_username": saved.smtp_username,
                "smtp_password": saved.smtp_password or values["smtp_password"],
                "smtp_starttls": saved.smtp_starttls,
                "smtp_ssl": saved.smtp_ssl,
                "email_from": saved.email_from or values["email_from"],
            })
    return values


def _send(recipient: str, subject: str, body: str, settings: dict) -> None:
    """Send one plain-text message through the configured authenticated SMTP relay."""
    if not settings["smtp_host"]:
        raise RuntimeError("SMTP_HOST is not configured")
    message = EmailMessage()
    message["From"] = settings["email_from"]
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    smtp_class = smtplib.SMTP_SSL if settings["smtp_ssl"] else smtplib.SMTP
    with smtp_class(settings["smtp_host"], settings["smtp_port"], timeout=20) as smtp:
        if settings["smtp_starttls"] and not settings["smtp_ssl"]:
            smtp.starttls()
        if settings["smtp_username"]:
            smtp.login(settings["smtp_username"], settings["smtp_password"])
        smtp.send_message(message)


async def send_email(recipient: str, subject: str, body: str) -> None:
    """Move blocking SMTP I/O off the FastAPI event loop."""
    settings = await _effective_mail_settings()
    await asyncio.to_thread(_send, recipient, subject, body, settings)
