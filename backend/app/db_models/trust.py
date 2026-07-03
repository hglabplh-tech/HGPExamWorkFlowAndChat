"""Trust-list, signature, private-PKI, and OCSP models.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


from .base import Base, UUIDMixin

class TrustList(UUIDMixin, Base):
    """Represent trustlist."""
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
    """Represent signaturevalidation."""
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
    """Represent privatepki."""
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
    """Represent usercertificate."""
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
    """Represent ocspquery."""
    __tablename__ = "ocsp_queries"
    private_pki_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_pkis.id"), index=True)
    serial_number: Mapped[str] = mapped_column(String(80), index=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    response_sha256: Mapped[str] = mapped_column(String(64))
    certificate_status: Mapped[str] = mapped_column(String(20), index=True)
    produced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
