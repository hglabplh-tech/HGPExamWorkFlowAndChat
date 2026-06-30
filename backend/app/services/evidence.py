# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for evidence."""
import hashlib
import json
import uuid
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def sha256_hex(content: bytes) -> str:
    """Perform the sha256 hex operation."""
    return hashlib.sha256(content).hexdigest()


def signature_message(
    examination_id: uuid.UUID,
    student_id: uuid.UUID,
    content_hash: str,
    signed_at: datetime,
    nonce: str,
    certificate_sha256: str | None = None,
) -> bytes:
    """Deterministic bytes signed by the student's locally held private key."""
    if signed_at.tzinfo is None:
        raise ValueError("Signing timestamp must include a timezone")
    canonical_time = signed_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    payload = {
        "content_sha256": content_hash,
        "certificate_sha256": certificate_sha256,
        "examination_id": str(examination_id),
        "nonce": nonce,
        "signed_at": canonical_time,
        "student_id": str(student_id),
        "version": 1,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def verify_ed25519(public_key_pem: bytes, signature: bytes, message: bytes) -> None:
    """Perform the verify ed25519 operation."""
    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("The registered key is not an Ed25519 public key")
    try:
        key.verify(signature, message)
    except InvalidSignature as error:
        raise ValueError("Examination signature is invalid") from error


def certificate_sha256(certificate_pem: bytes) -> str:
    """Perform the certificate sha256 operation."""
    certificate = x509.load_pem_x509_certificate(certificate_pem)
    return certificate.fingerprint(hashes.SHA256()).hex()


def certificate_matches_public_key(certificate_pem: bytes, public_key_pem: bytes) -> bool:
    """Perform the certificate matches public key operation."""
    certificate_key = x509.load_pem_x509_certificate(certificate_pem).public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    registered_key = serialization.load_pem_public_key(public_key_pem).public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return certificate_key == registered_key


def validate_public_key_pem(public_key_pem: bytes) -> None:
    """Perform the validate public key pem operation."""
    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, (Ed25519PublicKey, ec.EllipticCurvePublicKey, rsa.RSAPublicKey)):
        raise ValueError("Unsupported signing public key")


def verify_certificate_signature(certificate_pem: bytes, signature: bytes, message: bytes) -> str:
    """Perform the verify certificate signature operation."""
    try:
        certificate = x509.load_pem_x509_certificate(certificate_pem)
        key = certificate.public_key()
        if isinstance(key, Ed25519PublicKey):
            key.verify(signature, message)
            algorithm = "Ed25519"
        elif isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
            algorithm = "ECDSA-SHA256"
        elif isinstance(key, rsa.RSAPublicKey):
            key.verify(signature, message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
            algorithm = "RSA-PSS-SHA256"
        else:
            raise ValueError("Unsupported certificate public-key algorithm")
        now = datetime.now(UTC)
        if now < certificate.not_valid_before_utc or now > certificate.not_valid_after_utc:
            raise ValueError("Signing certificate is outside its validity period")
        return algorithm
    except (InvalidSignature, ValueError) as error:
        raise ValueError("Certificate signature verification failed") from error


def grading_signature_message(
    submission_id: uuid.UUID,
    exam_sha256: str,
    student_signature_sha256: str,
    grading_sha256: str,
    signed_at: datetime,
    certificate_fingerprint: str,
) -> bytes:
    """Perform the grading signature message operation."""
    if signed_at.tzinfo is None:
        raise ValueError("Signing timestamp must include a timezone")
    payload = {
        "certificate_sha256": certificate_fingerprint,
        "exam_sha256": exam_sha256,
        "grading_sha256": grading_sha256,
        "instructor_signed_at": signed_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "student_signature_sha256": student_signature_sha256,
        "submission_id": str(submission_id),
        "version": 1,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
