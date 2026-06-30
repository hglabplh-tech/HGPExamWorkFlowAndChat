"""Conversation, message, and research-sharing models.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


from .base import Base, Role, UUIDMixin

class Conversation(UUIDMixin, Base):
    """Represent conversation."""
    __tablename__ = "conversations"
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(20), default="direct")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class ConversationMember(Base):
    """Represent conversationmember."""
    __tablename__ = "conversation_members"
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


class Message(UUIDMixin, Base):
    """Represent message."""
    __tablename__ = "messages"
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    shared_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    shared_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ResearchInteraction(UUIDMixin, Base):
    """Represent researchinteraction."""
    __tablename__ = "research_interactions"
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    visibility: Mapped[str] = mapped_column(String(20), default="private", index=True)
    training_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
