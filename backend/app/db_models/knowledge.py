"""Curated document and video knowledge models.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


from .base import Base, UUIDMixin

class Document(UUIDMixin, Base):
    """Represent document."""
    __tablename__ = "documents"
    title: Mapped[str] = mapped_column(String(300), index=True)
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    media_type: Mapped[str] = mapped_column(String(120), default="text/plain")
    body_text: Mapped[str] = mapped_column(Text, default="")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    staff_approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    chunks: Mapped[list["DocumentChunk"]] = relationship(cascade="all, delete-orphan")


class DocumentChunk(UUIDMixin, Base):
    """Represent documentchunk."""
    __tablename__ = "document_chunks"
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str | None] = mapped_column(Text)  # indexed as tsvector in migration
    chroma_id: Mapped[str | None] = mapped_column(String(80), unique=True)


class VideoResource(UUIDMixin, Base):
    """Represent videoresource."""
    __tablename__ = "video_resources"
    __table_args__ = (UniqueConstraint("youtube_video_id", "course_id"),)
    youtube_video_id: Mapped[str] = mapped_column(String(20), index=True)
    youtube_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    discipline: Mapped[str] = mapped_column(String(120), index=True)
    question_tags: Mapped[list] = mapped_column(JSONB, default=list)
    keywords: Mapped[list] = mapped_column(JSONB, default=list)
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    staff_approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Thesaurus(UUIDMixin, Base):
    """Store JSON thesaurus entries used for full-text query expansion."""
    __tablename__ = "thesauri"
    __table_args__ = (UniqueConstraint("name", "language"),)
    name: Mapped[str] = mapped_column(String(120), index=True)
    language: Mapped[str] = mapped_column(String(20), default="simple", index=True)
    source_format: Mapped[str] = mapped_column(String(40), default="solr_synonyms")
    entries: Mapped[list] = mapped_column(JSONB, default=list)
    source_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
