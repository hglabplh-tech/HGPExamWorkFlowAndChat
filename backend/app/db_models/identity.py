"""User, course, and enrollment persistence models.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


from .base import Base, Role, UUIDMixin

class User(UUIDMixin, Base):
    """Represent user."""
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    matriculation_number: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    password_hash: Mapped[str]
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.student)
    permissions: Mapped[list] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    mobile_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    mobile_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_delivery_channel: Mapped[str] = mapped_column(String(12), default="email")
    registration_completed: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verification_code_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mobile_verification_code_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activation_token_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    activation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signing_public_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    client_cert_fingerprint: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActiveUserSession(UUIDMixin, Base):
    """Persist one authenticated login session for request-by-request checks."""
    __tablename__ = "active_user_sessions"
    __table_args__ = (UniqueConstraint("token_sha256"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_sha256: Mapped[str] = mapped_column(String(64), index=True)
    client_cert_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    auth_method: Mapped[str] = mapped_column(String(40), default="password_totp")
    request_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)


class Course(UUIDMixin, Base):
    """Represent course."""
    __tablename__ = "courses"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(240))
    discipline: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")


class Enrollment(UUIDMixin, Base):
    """Represent enrollment."""
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.student)
