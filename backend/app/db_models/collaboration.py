"""Conversation, message, and research-sharing models.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


from .base import Base, UUIDMixin

class Conversation(UUIDMixin, Base):
    """Represent conversation."""
    __tablename__ = "conversations"
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(20), default="direct")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(String(40), default="general", index=True)
    topic: Mapped[str | None] = mapped_column(String(300), nullable=True)
    examination_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("examinations.id"), nullable=True, index=True)
    random_assignment_seed: Mapped[str | None] = mapped_column(String(128), nullable=True)


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
    attachments: Mapped[list] = mapped_column(JSONB, default=list)
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


class ResearchHistory(UUIDMixin, Base):
    """Group one user's research and scoring actions inside an active session."""
    __tablename__ = "research_histories"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    active_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("active_user_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(160), default="New chat")
    stored: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ResearchHistoryEntry(UUIDMixin, Base):
    """Store one hybrid-search, research-question, or ASAG-scoring history item."""
    __tablename__ = "research_history_entries"
    history_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_histories.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    input_text: Mapped[str] = mapped_column(Text)
    refined_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ExamGroup(UUIDMixin, Base):
    """Bind a randomly assigned work group to an exam and X.509 identity."""
    __tablename__ = "exam_groups"
    __table_args__ = (UniqueConstraint("examination_id", "conversation_id"),)
    examination_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("examinations.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    topic: Mapped[str] = mapped_column(String(300))
    certificate_pem: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    certificate_sha256: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
