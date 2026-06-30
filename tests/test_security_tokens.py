"""Unit tests for password and evidence utilities.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import uuid
from datetime import UTC, datetime

import pytest
from argon2 import PasswordHasher

from backend.app.security import hash_password
from backend.app.services.evidence import sha256_hex, signature_message


def test_passwords_use_argon2id_and_verify() -> None:
    """Stored passwords use the modern Unix-style PHC string format."""
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert PasswordHasher().verify(encoded, "correct horse battery staple")


def test_signature_message_is_canonical_and_timezone_required() -> None:
    """Identical evidence fields produce identical signed bytes."""
    exam, student = uuid.uuid4(), uuid.uuid4()
    instant = datetime(2026, 1, 2, tzinfo=UTC)
    first = signature_message(exam, student, sha256_hex(b"exam"), instant, "nonce")
    second = signature_message(exam, student, sha256_hex(b"exam"), instant, "nonce")
    assert first == second
    with pytest.raises(ValueError):
        signature_message(exam, student, "0" * 64, datetime(2026, 1, 2), "nonce")
