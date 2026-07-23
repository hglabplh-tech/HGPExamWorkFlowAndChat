"""Examination, question, submission, and grading models.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


from .base import Base, UUIDMixin

class Examination(UUIDMixin, Base):
    """Represent examination."""
    __tablename__ = "examinations"
    __table_args__ = (UniqueConstraint("course_id", "title"),)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(300))
    instructions: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="practice", index=True)
    state: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_set_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exam_rule_sets.id"), nullable=True)


class ExamRuleSet(UUIDMixin, Base):
    """Store a versioned, reviewable scoring and format rules file."""
    __tablename__ = "exam_rule_sets"
    __table_args__ = (UniqueConstraint("course_id", "name", "version"),)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer)
    rules: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ExamQuestion(UUIDMixin, Base):
    """Represent examquestion."""
    __tablename__ = "exam_questions"
    examination_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("examinations.id", ondelete="CASCADE"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str] = mapped_column(Text)
    required_keywords: Mapped[list] = mapped_column(JSONB, default=list)
    expected_facts: Mapped[list] = mapped_column(JSONB, default=list)
    max_score: Mapped[float] = mapped_column()
    question_type: Mapped[str] = mapped_column(String(30), default="free_text", index=True)
    question_category: Mapped[str] = mapped_column(String(30), default="description", index=True)
    choices: Mapped[list] = mapped_column(JSONB, default=list)
    correct_options: Mapped[list] = mapped_column(JSONB, default=list)
    partial_credit: Mapped[bool] = mapped_column(Boolean, default=False)


class DisciplineScoringProfile(UUIDMixin, Base):
    """Represent disciplinescoringprofile."""
    __tablename__ = "discipline_scoring_profiles"
    __table_args__ = (UniqueConstraint("discipline", "version"),)
    discipline: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer)
    grading_weights: Mapped[dict] = mapped_column(JSONB)
    search_weights: Mapped[dict] = mapped_column(JSONB)
    semantic_profile: Mapped[str] = mapped_column(String(20), default="economy")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Submission(UUIDMixin, Base):
    """Represent submission."""
    __tablename__ = "submissions"
    examination_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("examinations.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    answers: Mapped[dict] = mapped_column(JSONB)
    ai_grade: Mapped[dict | None] = mapped_column(JSONB)
    teacher_grade: Mapped[dict | None] = mapped_column(JSONB)
    encrypted_answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    encrypted_content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    encrypted_ai_grade: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    encrypted_teacher_grade: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    encryption_recipients: Mapped[list] = mapped_column(JSONB, default=list)
    encryption_status: Mapped[str] = mapped_column(String(40), default="pending")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str] = mapped_column(String(120), default="application/json")
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    student_signature: Mapped[bytes] = mapped_column(LargeBinary)
    student_certificate_pem: Mapped[bytes] = mapped_column(LargeBinary)
    signature_algorithm: Mapped[str] = mapped_column(String(40), default="Ed25519")
    client_signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    receipt_nonce: Mapped[str] = mapped_column(String(128), unique=True)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    feedback_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grading_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instructor_signature: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    instructor_certificate_pem: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    instructor_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_pdf: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    report_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correction_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"), nullable=True)
    academic_integrity_review: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    exam_group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exam_groups.id"), nullable=True, index=True)
    group_certificate_pem: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class SubmissionConfirmation(UUIDMixin, Base):
    """Store a short-lived, one-use confirmation for a real exam file."""
    __tablename__ = "submission_confirmations"
    examination_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("examinations.id"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GradeEvent(UUIDMixin, Base):
    """Append-only grading history; never update or delete these records."""
    __tablename__ = "grade_events"
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(40))
    grade: Mapped[dict] = mapped_column(JSONB)
    encrypted_grade: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
