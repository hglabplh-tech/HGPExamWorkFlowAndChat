"""Envelope-encryption tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from backend.app.services.envelope_encryption import encrypt_json_for_certificate


def _rsa_certificate_pem() -> bytes:
    """Create a short-lived RSA certificate suitable for encryption tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Student")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM)


def test_exam_payload_encryption_envelope_uses_certificate_recipient() -> None:
    """Sensitive exam data is stored as a certificate-bound AES-GCM envelope."""
    envelope = encrypt_json_for_certificate({"answer": "secret"}, _rsa_certificate_pem(), "submission.answers")
    assert envelope["algorithm"] == "AES-256-GCM"
    assert envelope["key_wrap"] == "RSA-OAEP-SHA256"
    assert envelope["purpose"] == "submission.answers"
    assert envelope["ciphertext"] != "secret"
