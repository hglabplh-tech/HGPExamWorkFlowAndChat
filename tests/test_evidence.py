# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for test evidence."""
import uuid
from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.app.services.evidence import sha256_hex, signature_message, verify_ed25519


def test_signed_exam_receipt_verifies_and_detects_changes():
    """Verify signed exam receipt verifies and detects changes."""
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    examination_id, student_id = uuid.uuid4(), uuid.uuid4()
    message = signature_message(examination_id, student_id, sha256_hex(b"exam"), datetime.now(UTC), "n" * 24)
    signature = private_key.sign(message)
    verify_ed25519(public_pem, signature, message)

    try:
        verify_ed25519(public_pem, signature, message + b"changed")
    except ValueError:
        pass
    else:
        raise AssertionError("A modified receipt must not verify")
