# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Persistent authentication and TOTP session services."""
import hashlib
import hmac
import base64
import secrets
import struct
import time
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import ActiveUserSession, User

hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def normalize_certificate_fingerprint(value: str | None) -> str | None:
    """Normalize a presented X.509 certificate fingerprint for comparison."""
    return value.replace(":", "").lower() if value else None


def token_sha256(token: str) -> str:
    """Hash a bearer token before storing or looking it up in PostgreSQL."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_numeric_code() -> str:
    """Generate a six-digit verification code for email, SMS, or TOTP-style delivery."""
    return f"{secrets.randbelow(1_000_000):06d}"


def issue_access_token(user: User) -> str:
    """Create a short-lived signed bearer token for a persisted login session."""
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user.id), "role": user.role.value, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def verify_totp_code(secret: str, code: str, *, window: int = 1, now: int | None = None) -> bool:
    """Verify an RFC 6238 six-digit authenticator-app code."""
    if not code or not code.isdigit() or len(code) != 6:
        return False
    timestamp = int(now if now is not None else time.time())
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_totp_at(secret, timestamp // 30 + offset), code):
            return True
    return False


def fresh_totp_code(secret: str, *, now: int | None = None) -> dict:
    """Generate the current backend-side TOTP value and its expiry metadata."""
    timestamp = int(now if now is not None else time.time())
    counter = timestamp // 30
    expires_in = 30 - (timestamp % 30)
    return {
        "totp_code": _totp_at(secret, counter),
        "period_seconds": 30,
        "expires_in_seconds": expires_in,
        "valid_until": datetime.fromtimestamp(timestamp + expires_in, UTC),
    }


def _totp_at(secret: str, counter: int) -> str:
    """Calculate one TOTP value for one time counter."""
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


async def authenticate_password_only(db: AsyncSession, *, user_id: str, password: str, allow_inactive: bool = False) -> User:
    """Verify a user id and password without consuming or checking a TOTP code."""
    user = await db.scalar(select(User).where(User.email == user_id))
    if not user or (not allow_inactive and not user.active):
        raise ValueError("Invalid credentials")
    try:
        valid_password = hasher.verify(user.password_hash, password)
    except Exception:
        valid_password = False
    if not valid_password:
        raise ValueError("Invalid credentials")
    return user


async def login_with_password(
    db: AsyncSession,
    *,
    user_id: str,
    password: str,
    totp_code: str | None = None,
    client_cert_fingerprint: str | None = None,
    request_metadata: dict | None = None,
) -> tuple[User, str, ActiveUserSession]:
    """Authenticate a user and persist a revocable active login session."""
    user = await authenticate_password_only(db, user_id=user_id, password=password)
    if not user.registration_completed:
        raise ValueError("Account registration is not completed")
    if user.totp_enabled and not verify_totp_code(user.totp_secret or "", totp_code or ""):
        raise ValueError("Invalid TOTP code")
    normalized_cert = normalize_certificate_fingerprint(client_cert_fingerprint)
    if normalized_cert and user.client_cert_fingerprint and not hmac.compare_digest(user.client_cert_fingerprint, normalized_cert):
        raise ValueError("Client certificate does not belong to this account")
    token = issue_access_token(user)
    now = datetime.now(UTC)
    settings = get_settings()
    session = ActiveUserSession(
        user_id=user.id,
        token_sha256=token_sha256(token),
        client_cert_fingerprint=normalized_cert,
        issued_at=now,
        expires_at=now + timedelta(minutes=settings.access_token_minutes),
        last_seen_at=now,
        auth_method="password_totp" if user.totp_enabled else "password",
        request_metadata=request_metadata or {},
    )
    db.add(session)
    return user, token, session


async def active_session_for_token(
    db: AsyncSession,
    *,
    token: str,
    client_cert_fingerprint: str | None = None,
) -> ActiveUserSession | None:
    """Return the active session that proves a bearer token was issued and not logged out."""
    now = datetime.now(UTC)
    await db.execute(delete(ActiveUserSession).where(ActiveUserSession.expires_at < now))
    session = await db.scalar(select(ActiveUserSession).where(
        ActiveUserSession.token_sha256 == token_sha256(token),
        ActiveUserSession.revoked_at.is_(None),
        ActiveUserSession.expires_at >= now,
    ))
    if not session:
        return None
    normalized_cert = normalize_certificate_fingerprint(client_cert_fingerprint)
    if session.client_cert_fingerprint and not hmac.compare_digest(session.client_cert_fingerprint, normalized_cert or ""):
        return None
    session.last_seen_at = now
    return session


async def logout_token(db: AsyncSession, *, token: str) -> bool:
    """Invalidate one active session so the bearer token no longer works."""
    session = await db.scalar(select(ActiveUserSession).where(
        ActiveUserSession.token_sha256 == token_sha256(token),
        ActiveUserSession.revoked_at.is_(None),
    ))
    if not session:
        return False
    await db.delete(session)
    return True
