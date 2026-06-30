"""Training example and model-run registry models.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


from .base import Base, Role, UUIDMixin

class TrainingExample(UUIDMixin, Base):
    """Represent trainingexample."""
    __tablename__ = "training_examples"
    __table_args__ = (UniqueConstraint("source_type", "source_id", "task"),)
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    task: Mapped[str] = mapped_column(String(40), index=True)
    discipline: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ModelTrainingRun(UUIDMixin, Base):
    """Represent modeltrainingrun."""
    __tablename__ = "model_training_runs"
    task: Mapped[str] = mapped_column(String(40), index=True)
    discipline: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    example_count: Mapped[int] = mapped_column(Integer, default=0)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
