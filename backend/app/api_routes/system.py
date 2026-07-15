"""Administrative system-configuration REST endpoints.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import MailServerSettings, User
from ..schemas import LoggingSettingsIn, LoggingSettingsOut, MailServerSettingsIn, MailServerSettingsOut
from ..security import require_nonce, authenticate
from ..services.audit import append_audit
from ..services.authorization import has_permission
from ..services.configuration_cache import cached_mail_settings, cache_status, invalidate_configuration
from ..services.logging_config import configure_logging, current_logging_config
from .common import require_admin

router = APIRouter(prefix="/api/v1")


def _public_mail_settings(settings: MailServerSettings) -> MailServerSettingsOut:
    """Return a password-redacted mail configuration DTO."""
    return MailServerSettingsOut(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_username=settings.smtp_username,
        smtp_password_set=bool(settings.smtp_password),
        smtp_starttls=settings.smtp_starttls,
        smtp_ssl=settings.smtp_ssl,
        email_from=settings.email_from,
        support_email=settings.support_email,
        imap_host=settings.imap_host,
        imap_port=settings.imap_port,
        imap_username=settings.imap_username,
        imap_password_set=bool(settings.imap_password),
        imap_ssl=settings.imap_ssl,
        active=settings.active,
    )


async def _mail_settings(db: AsyncSession) -> MailServerSettings | None:
    """Load the default administrator-managed mail settings row."""
    return await db.scalar(select(MailServerSettings).where(MailServerSettings.name == "default"))


def _public_cached_mail_settings(settings) -> MailServerSettingsOut:
    """Return a password-redacted DTO from a cached mail-settings snapshot."""
    return MailServerSettingsOut(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_username=settings.smtp_username,
        smtp_password_set=bool(settings.smtp_password),
        smtp_starttls=settings.smtp_starttls,
        smtp_ssl=settings.smtp_ssl,
        email_from=settings.email_from,
        support_email=settings.support_email,
        imap_host=settings.imap_host,
        imap_port=settings.imap_port,
        imap_username=settings.imap_username,
        imap_password_set=bool(settings.imap_password),
        imap_ssl=settings.imap_ssl,
        active=settings.active,
    )


@router.get("/admin/mail-settings", response_model=MailServerSettingsOut)
async def get_mail_settings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """Return the active SMTP/IMAP settings for the admin mask."""
    require_admin(user)
    settings = await cached_mail_settings(db, include_inactive=True)
    if settings:
        return _public_cached_mail_settings(settings)
    return MailServerSettingsOut(
        smtp_host=None,
        smtp_port=587,
        smtp_username=None,
        smtp_password_set=False,
        smtp_starttls=True,
        smtp_ssl=False,
        email_from=None,
        support_email=None,
        imap_host=None,
        imap_port=993,
        imap_username=None,
        imap_password_set=False,
        imap_ssl=True,
        active=True,
    )


@router.put("/admin/mail-settings", response_model=MailServerSettingsOut)
async def save_mail_settings(
    data: MailServerSettingsIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Create or update SMTP/IMAP settings from the administrator mask."""
    require_admin(user)
    settings = await _mail_settings(db)
    if not settings:
        settings = MailServerSettings(name="default")
        db.add(settings)
    settings.smtp_host = data.smtp_host
    settings.smtp_port = data.smtp_port
    settings.smtp_username = data.smtp_username
    if data.smtp_password:
        settings.smtp_password = data.smtp_password
    settings.smtp_starttls = data.smtp_starttls
    settings.smtp_ssl = data.smtp_ssl
    settings.email_from = data.email_from
    settings.support_email = data.support_email
    settings.imap_host = data.imap_host
    settings.imap_port = data.imap_port
    settings.imap_username = data.imap_username
    if data.imap_password:
        settings.imap_password = data.imap_password
    settings.imap_ssl = data.imap_ssl
    settings.active = data.active
    settings.updated_by = user.id
    settings.updated_at = datetime.utcnow()
    await db.flush()
    await append_audit(
        db,
        user.id,
        "mail_settings_updated",
        "mail_server_settings",
        settings.id,
        details={
            "smtp_host": settings.smtp_host,
            "imap_host": settings.imap_host,
            "active": settings.active,
            "can_send_email": has_permission(user, "email.send"),
        },
    )
    await db.commit()
    await db.refresh(settings)
    invalidate_configuration("mail")
    return _public_mail_settings(settings)


@router.get("/admin/logging-settings", response_model=LoggingSettingsOut)
async def get_logging_settings(user: User = Depends(authenticate)):
    """Return the active standard-library logging configuration for administrators."""
    require_admin(user)
    return LoggingSettingsOut(**current_logging_config())


@router.put("/admin/logging-settings", response_model=LoggingSettingsOut)
async def save_logging_settings(
    data: LoggingSettingsIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Apply runtime logging settings; only administrators may change them."""
    require_admin(user)
    invalidate_configuration("logging")
    applied = configure_logging(data.level, data.log_file_path, data.debug_values)
    await append_audit(
        db,
        user.id,
        "logging_settings_updated",
        "runtime_logging",
        user.id,
        details={
            "level": applied["level"],
            "log_file_path": applied.get("log_file_path"),
            "debug_values": applied.get("debug_values"),
        },
    )
    await db.commit()
    return LoggingSettingsOut(**applied)


@router.get("/admin/configuration-cache")
async def get_configuration_cache_status(user: User = Depends(authenticate)):
    """Return configuration-cache status for administrators."""
    require_admin(user)
    return cache_status()


@router.post("/admin/configuration-cache/invalidate")
async def invalidate_configuration_cache(
    section: str | None = None,
    user: User = Depends(require_nonce),
):
    """Invalidate all configuration cache entries or one named section."""
    require_admin(user)
    invalidate_configuration(section)
    return {"status": "invalidated", "section": section or "all", "cache": cache_status()}
