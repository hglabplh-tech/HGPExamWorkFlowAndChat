"""Declarative base classes and shared roles.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Represent base."""
    pass


class Role(str, enum.Enum):
    """Represent role."""
    student = "student"
    teacher = "teacher"
    staff = "staff"
    admin = "admin"


class UUIDMixin:
    """Represent uuidmixin."""
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
