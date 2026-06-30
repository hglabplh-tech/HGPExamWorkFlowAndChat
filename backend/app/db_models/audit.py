"""Append-only audit and replay-protection models.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


from .base import Base, Role, UUIDMixin

class AuditEvent(UUIDMixin, Base):
    """Represent auditevent."""
    __tablename__ = "audit_events"
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class RequestNonce(Base):
    """Represent requestnonce."""
    __tablename__ = "request_nonces"
    nonce: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
