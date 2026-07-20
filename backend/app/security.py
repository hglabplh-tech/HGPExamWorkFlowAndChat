# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for security."""
import secrets
import uuid
import base64
import hmac
import hashlib
import struct
import time
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from jwt import InvalidTokenError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_db
from .models import ActiveUserSession, RequestNonce, User
from .services.authentication import active_session_for_token, normalize_certificate_fingerprint

basic = HTTPBasic(auto_error=False)
bearer = HTTPBearer(auto_error=False)
# Argon2id encoded in the self-describing Unix/PHC modular format:
# $argon2id$v=19$m=19456,t=2,p=1$<salt>$<hash>
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def hash_password(password: str) -> str:
    """Perform the hash password operation."""
    return hasher.hash(password)


def create_access_token(user: User) -> str:
    """Perform the create access token operation."""
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user.id), "role": user.role.value, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def generate_totp_secret() -> str:
    """Create a Base32 secret suitable for authenticator applications."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_uri(secret: str, email: str, issuer: str = "HGPExamWorkFlowAndChat") -> str:
    """Build an otpauth URI for enrollment QR-code generation by clients."""
    return f"otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


def verify_totp(secret: str, code: str, *, window: int = 1, now: int | None = None) -> bool:
    """Verify a six-digit time-based one-time password with small clock tolerance."""
    if not code or not code.isdigit() or len(code) != 6:
        return False
    timestamp = int(now if now is not None else time.time())
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_totp_at(secret, timestamp // 30 + offset), code):
            return True
    return False


def _totp_at(secret: str, counter: int) -> str:
    """Calculate the RFC 6238 TOTP value for one counter."""
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def decode_user_id(token: str) -> uuid.UUID:
    """Perform the decode user id operation."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=["HS256"],
        )
        return uuid.UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError) as error:
        raise ValueError("Invalid access token") from error


async def authenticate(
    basic_credentials: HTTPBasicCredentials | None = Depends(basic),
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    client_cert_fingerprint: str | None = Header(default=None, alias="X-Client-Cert-Fingerprint"),
    totp_code: str | None = Header(default=None, alias="X-TOTP-Code"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate one HTTP RPC request against a live session or trusted certificate."""
    user: User | None = None
    settings = get_settings()
    if bearer_credentials:
        try:
            session = await active_session_for_token(
                db,
                token=bearer_credentials.credentials,
                client_cert_fingerprint=client_cert_fingerprint,
            )
            if session:
                user = await db.get(User, decode_user_id(bearer_credentials.credentials))
                if user and session.user_id != user.id:
                    user = None
        except ValueError:
            pass
    elif client_cert_fingerprint and settings.client_certificate_auth_enabled:
        normalized_fingerprint = normalize_certificate_fingerprint(client_cert_fingerprint)
        user = await db.scalar(
            select(User).where(User.client_cert_fingerprint == normalized_fingerprint)
        )
    elif basic_credentials and settings.password_auth_enabled:
        user = await db.scalar(select(User).where(User.email == basic_credentials.username))
        if user:
            try:
                valid = hasher.verify(user.password_hash, basic_credentials.password)
            except Exception:
                valid = False
            if not valid:
                user = None
            elif user.totp_enabled and not verify_totp(user.totp_secret or "", totp_code or ""):
                user = None
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return user


async def current_active_session(
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    client_cert_fingerprint: str | None = Header(default=None, alias="X-Client-Cert-Fingerprint"),
    db: AsyncSession = Depends(get_db),
) -> ActiveUserSession | None:
    """Return the active session associated with the request bearer token, if any."""
    if not bearer_credentials:
        return None
    return await active_session_for_token(
        db,
        token=bearer_credentials.credentials,
        client_cert_fingerprint=client_cert_fingerprint,
    )


async def require_nonce(
    user: User = Depends(authenticate),
    nonce: str = Header(alias="X-Request-Nonce", min_length=16, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> User:
    # A unique nonce makes retries explicit and prevents replay of write requests.
    """Perform the require nonce operation."""
    cutoff = datetime.now(UTC) - timedelta(seconds=get_settings().nonce_ttl_seconds)
    await db.execute(delete(RequestNonce).where(RequestNonce.used_at < cutoff))
    if await db.get(RequestNonce, nonce):
        raise HTTPException(status.HTTP_409_CONFLICT, "Request nonce has already been used")
    db.add(RequestNonce(nonce=nonce, user_id=user.id))
    await db.commit()
    return user


def new_nonce() -> str:
    """Perform the new nonce operation."""
    return secrets.token_urlsafe(24)
