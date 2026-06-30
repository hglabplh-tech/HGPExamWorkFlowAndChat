"""User, course, and enrollment persistence models.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


from .base import Base, Role, UUIDMixin

class User(UUIDMixin, Base):
    """Represent user."""
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str]
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.student)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    signing_public_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    client_cert_fingerprint: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
