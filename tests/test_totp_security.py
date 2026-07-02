"""TOTP security tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from backend.app.security import generate_totp_secret, totp_uri, verify_totp, _totp_at
from backend.app.services.authentication import fresh_totp_code, new_numeric_code, verify_totp_code


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


def test_backend_fresh_totp_can_be_checked_independently() -> None:
    """Backend-issued fresh TOTP values verify through the auth-service checker."""
    secret = generate_totp_secret()
    now = 1_800_000_015
    fresh = fresh_totp_code(secret, now=now)
    assert fresh["expires_in_seconds"] == 15
    assert verify_totp_code(secret, fresh["totp_code"], window=0, now=now)


def test_registration_codes_are_six_digit_numbers() -> None:
    """Registration email/SMS verification codes use the expected login-code shape."""
    code = new_numeric_code()
    assert code.isdigit()
    assert len(code) == 6
