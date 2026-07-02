"""TOTP security tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from backend.app.security import generate_totp_secret, totp_uri, verify_totp, _totp_at


def test_totp_secret_and_uri_are_authenticator_compatible() -> None:
    """Generated TOTP material can be enrolled in authenticator apps."""
    secret = generate_totp_secret()
    uri = totp_uri(secret, "admin@example.org")
    assert secret
    assert "otpauth://totp/" in uri
    assert secret in uri


def test_totp_verification_accepts_current_code() -> None:
    """A valid six-digit TOTP code verifies for the current time window."""
    secret = generate_totp_secret()
    now = 1_800_000_000
    assert verify_totp(secret, _totp_at(secret, now // 30), now=now)
    assert not verify_totp(secret, "000000", window=0, now=now)
