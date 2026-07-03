"""Declarative base classes and shared roles.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import enum
import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
