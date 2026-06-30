# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for security."""
import secrets
import uuid
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
from .models import RequestNonce, User

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
    db: AsyncSession = Depends(get_db),
) -> User:
    """Perform the authenticate operation."""
    user: User | None = None
    if bearer_credentials:
        try:
            user = await db.get(User, decode_user_id(bearer_credentials.credentials))
        except ValueError:
            pass
    elif client_cert_fingerprint:
        normalized_fingerprint = client_cert_fingerprint.replace(":", "").lower()
        user = await db.scalar(
            select(User).where(User.client_cert_fingerprint == normalized_fingerprint)
        )
    elif basic_credentials:
        user = await db.scalar(select(User).where(User.email == basic_credentials.username))
        if user:
            try:
                valid = hasher.verify(user.password_hash, basic_credentials.password)
            except Exception:
                valid = False
            if not valid:
                user = None
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return user


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
