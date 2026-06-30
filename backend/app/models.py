import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    staff = "staff"
    admin = "admin"


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(UUIDMixin, Base):
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
    __tablename__ = "courses"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(240))
    discipline: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")


class Enrollment(UUIDMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.student)


class Document(UUIDMixin, Base):
    __tablename__ = "documents"
    title: Mapped[str] = mapped_column(String(300), index=True)
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text, default="")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    staff_approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    chunks: Mapped[list["DocumentChunk"]] = relationship(cascade="all, delete-orphan")


class DocumentChunk(UUIDMixin, Base):
    __tablename__ = "document_chunks"
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str | None] = mapped_column(Text)  # indexed as tsvector in migration
    chroma_id: Mapped[str | None] = mapped_column(String(80), unique=True)


class VideoResource(UUIDMixin, Base):
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


class Examination(UUIDMixin, Base):
    __tablename__ = "examinations"
    __table_args__ = (UniqueConstraint("course_id", "title"),)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(300))
    instructions: Mapped[str] = mapped_column(Text, default="")


class ExamQuestion(UUIDMixin, Base):
    __tablename__ = "exam_questions"
    examination_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("examinations.id", ondelete="CASCADE"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str] = mapped_column(Text)
    required_keywords: Mapped[list] = mapped_column(JSONB, default=list)
    expected_facts: Mapped[list] = mapped_column(JSONB, default=list)
    max_score: Mapped[float] = mapped_column()


class DisciplineScoringProfile(UUIDMixin, Base):
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
    __tablename__ = "submissions"
    examination_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("examinations.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    answers: Mapped[dict] = mapped_column(JSONB)
    ai_grade: Mapped[dict | None] = mapped_column(JSONB)
    teacher_grade: Mapped[dict | None] = mapped_column(JSONB)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str] = mapped_column(String(120), default="application/json")
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    student_signature: Mapped[bytes] = mapped_column(LargeBinary)
    signature_algorithm: Mapped[str] = mapped_column(String(40), default="Ed25519")
    client_signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    receipt_nonce: Mapped[str] = mapped_column(String(128), unique=True)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class GradeEvent(UUIDMixin, Base):
    """Append-only grading history; never update or delete these records."""
    __tablename__ = "grade_events"
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(40))
    grade: Mapped[dict] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Conversation(UUIDMixin, Base):
    __tablename__ = "conversations"
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(20), default="direct")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


class Message(UUIDMixin, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    shared_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    shared_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AuditEvent(UUIDMixin, Base):
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
    __tablename__ = "request_nonces"
    nonce: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TrustList(UUIDMixin, Base):
    __tablename__ = "trust_lists"
    name: Mapped[str] = mapped_column(String(240))
    framework: Mapped[str] = mapped_column(String(40), index=True)
    territory: Mapped[str | None] = mapped_column(String(12), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    xml_content: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    tsl_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    signature_status: Mapped[str] = mapped_column(String(40), default="not_validated")
    validation_report: Mapped[dict] = mapped_column(JSONB, default=dict)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SignatureValidation(UUIDMixin, Base):
    __tablename__ = "signature_validations"
    document_sha256: Mapped[str] = mapped_column(String(64), index=True)
    framework: Mapped[str] = mapped_column(String(40), index=True)
    signature_format: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), index=True)
    qualification: Mapped[str | None] = mapped_column(String(80), nullable=True)
    signer_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    trusted_list_ids: Mapped[list] = mapped_column(JSONB, default=list)
    report: Mapped[dict] = mapped_column(JSONB, default=dict)
    validated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PrivatePKI(UUIDMixin, Base):
    __tablename__ = "private_pkis"
    name: Mapped[str] = mapped_column(String(240), unique=True)
    root_certificate_pem: Mapped[bytes] = mapped_column(LargeBinary)
    intermediate_bundle_pem: Mapped[bytes] = mapped_column(LargeBinary, default=b"")
    root_sha256_fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_status: Mapped[str] = mapped_column(String(40), default="not_validated")
    ocsp_responder_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocsp_responder_certificate_pem: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class UserCertificate(UUIDMixin, Base):
    __tablename__ = "user_certificates"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    private_pki_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_pkis.id"))
    certificate_pem: Mapped[bytes] = mapped_column(LargeBinary)
    sha256_fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    subject: Mapped[str] = mapped_column(Text)
    serial_number: Mapped[str] = mapped_column(String(80))
    not_valid_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    not_valid_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class OCSPQuery(UUIDMixin, Base):
    __tablename__ = "ocsp_queries"
    private_pki_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_pkis.id"), index=True)
    serial_number: Mapped[str] = mapped_column(String(80), index=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    response_sha256: Mapped[str] = mapped_column(String(64))
    certificate_status: Mapped[str] = mapped_column(String(20), index=True)
    produced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
