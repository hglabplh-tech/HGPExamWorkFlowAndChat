"""System-wide administration settings.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDMixin


class MailServerSettings(UUIDMixin, Base):
    """Store administrator-managed SMTP and IMAP connection settings."""
    __tablename__ = "mail_server_settings"

    name: Mapped[str] = mapped_column(String(120), default="default", unique=True, index=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    smtp_starttls: Mapped[bool] = mapped_column(Boolean, default=True)
    smtp_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    email_from: Mapped[str | None] = mapped_column(String(320), nullable=True)
    support_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    imap_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_password: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    imap_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
