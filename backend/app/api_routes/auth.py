# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Authentication REST endpoints for login, logout, and active sessions."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..security import authenticate
from ..services.audit import append_audit
from ..services.authentication import authenticate_password_only, fresh_totp_code, login_with_password, logout_token, verify_totp_code

router = APIRouter(prefix="/api/v1")
basic = HTTPBasic(auto_error=False)
bearer = HTTPBearer(auto_error=False)


@router.post("/auth/token")
async def login(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(basic),
    totp_code: str | None = Header(default=None, alias="X-TOTP-Code"),
    client_cert_fingerprint: str | None = Header(default=None, alias="X-Client-Cert-Fingerprint"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Authenticate basic credentials plus optional TOTP and create an active session."""
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Basic credentials required")
    metadata = {
        "client_host": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    try:
        user, access_token, session = await login_with_password(
            db,
            user_id=credentials.username,
            password=credentials.password,
            totp_code=totp_code,
            client_cert_fingerprint=client_cert_fingerprint,
            request_metadata=metadata,
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    await append_audit(db, user.id, "login_session_started", "user", user.id, details={"session_id": str(session.id)})
    await db.commit()
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role.value,
        "display_name": user.display_name,
        "session_id": session.id,
        "expires_at": session.expires_at,
    }


@router.post("/auth/check_totp")
async def check_totp(
    credentials: HTTPBasicCredentials | None = Depends(basic),
    totp_code: str | None = Header(default=None, alias="X-TOTP-Code"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Check a TOTP code in the backend before attempting a full login."""
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Basic credentials required")
    try:
        user = await authenticate_password_only(db, user_id=credentials.username, password=credentials.password)
    except ValueError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status.HTTP_409_CONFLICT, "TOTP is not enabled for this account")
    valid = verify_totp_code(user.totp_secret, totp_code or "")
    await append_audit(db, user.id, "totp_checked", "user", user.id, details={"valid": valid})
    await db.commit()
    return {"valid": valid, "enabled": True}


@router.post("/auth/get_fresh_totp")
async def get_fresh_totp(
    credentials: HTTPBasicCredentials | None = Depends(basic),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate a fresh backend-side TOTP code after password verification."""
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Basic credentials required")
    try:
        user = await authenticate_password_only(db, user_id=credentials.username, password=credentials.password)
    except ValueError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status.HTTP_409_CONFLICT, "TOTP is not enabled for this account")
    fresh = fresh_totp_code(user.totp_secret)
    await append_audit(db, user.id, "fresh_totp_requested", "user", user.id, details={"valid_until": fresh["valid_until"].isoformat()})
    await db.commit()
    return {"enabled": True, **fresh}


@router.post("/auth/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
) -> dict:
    """Logout the current active session by deleting its persisted token hash."""
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")
    deleted = await logout_token(db, token=credentials.credentials)
    await append_audit(db, user.id, "login_session_ended", "user", user.id)
    await db.commit()
    return {"status": "logged_out", "deleted": deleted}
