# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Authentication RPC-over-HTTP endpoints for login, logout, and active sessions."""
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from ..config import get_settings
from ..schemas import RegistrationStart, RegistrationVerify
from ..security import authenticate
from ..services.audit import append_audit
from ..services.authentication import authenticate_password_only, fresh_totp_code, login_with_password, logout_token, new_numeric_code, token_sha256, verify_totp_code
from ..services.email_delivery import send_email
from ..services.sms_delivery import send_sms

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


@router.post("/auth/register/start")
async def start_registration(
    data: RegistrationStart,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start registration for an administrator-created inactive user."""
    try:
        user = await authenticate_password_only(db, user_id=data.user_id, password=data.password, allow_inactive=True)
    except ValueError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    if user.registration_completed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Account is already registered")
    email_code = new_numeric_code()
    mobile_code = new_numeric_code() if data.mobile_number else None
    user.contact_email = data.contact_email
    user.mobile_number = data.mobile_number
    user.email_verified = False
    user.mobile_verified = False if data.mobile_number else True
    user.email_verification_code_sha256 = token_sha256(email_code)
    user.mobile_verification_code_sha256 = token_sha256(mobile_code) if mobile_code else None
    user.verification_expires_at = datetime.now(UTC) + timedelta(minutes=get_settings().registration_activation_minutes)
    try:
        await send_email(data.contact_email, "HGPExamWorkFlowAndChat registration code", f"Your registration email code is: {email_code}")
        if data.mobile_number and mobile_code:
            await send_sms(data.mobile_number, f"HGPExamWorkFlowAndChat registration SMS code: {mobile_code}")
    except Exception as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    await append_audit(db, user.id, "registration_codes_sent", "user", user.id, details={"email": True, "sms": bool(data.mobile_number)})
    await db.commit()
    return {"status": "codes_sent", "email_required": True, "sms_required": bool(data.mobile_number), "expires_at": user.verification_expires_at}


@router.post("/auth/register/verify")
async def verify_registration(
    data: RegistrationVerify,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify contact codes and send a 30-minute activation link."""
    try:
        user = await authenticate_password_only(db, user_id=data.user_id, password=data.password, allow_inactive=True)
    except ValueError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    if user.registration_completed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Account is already registered")
    now = datetime.now(UTC)
    if not user.verification_expires_at or user.verification_expires_at < now:
        raise HTTPException(status.HTTP_410_GONE, "Registration verification codes expired")
    if not user.email_verification_code_sha256 or not hmac.compare_digest(user.email_verification_code_sha256, token_sha256(data.email_code)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid email verification code")
    if user.mobile_number:
        if not data.mobile_code or not user.mobile_verification_code_sha256 or not hmac.compare_digest(user.mobile_verification_code_sha256, token_sha256(data.mobile_code)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid SMS verification code")
    elif data.totp_delivery_channel == "sms":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "SMS TOTP requires a verified mobile number")
    token = secrets.token_urlsafe(32)
    user.email_verified = True
    user.mobile_verified = bool(user.mobile_number)
    user.totp_delivery_channel = data.totp_delivery_channel
    user.activation_token_sha256 = token_sha256(token)
    user.activation_expires_at = now + timedelta(minutes=get_settings().registration_activation_minutes)
    activation_link = f"{get_settings().public_base_url}/api/v1/auth/register/activate?token={token}"
    try:
        await send_email(user.contact_email or user.email, "Activate HGPExamWorkFlowAndChat account", f"Activate your account within 30 minutes:\n\n{activation_link}")
    except Exception as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    await append_audit(db, user.id, "registration_verified", "user", user.id, details={"totp_delivery_channel": user.totp_delivery_channel})
    await db.commit()
    return {"status": "activation_link_sent", "activation_expires_at": user.activation_expires_at}


@router.get("/auth/register/activate")
async def activate_registration(
    token: str = Query(min_length=20),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Activate a registered user through a time-limited email link."""
    token_hash = token_sha256(token)
    user = await db.scalar(select(User).where(User.activation_token_sha256 == token_hash))
    if not user or not user.activation_expires_at or user.activation_expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "Activation link is invalid or expired")
    user.active = True
    user.registration_completed = True
    user.totp_enabled = True
    user.activation_token_sha256 = None
    user.activation_expires_at = None
    user.email_verification_code_sha256 = None
    user.mobile_verification_code_sha256 = None
    user.verification_expires_at = None
    await append_audit(db, user.id, "registration_activated", "user", user.id)
    await db.commit()
    return {"status": "activated", "user_id": user.email}


@router.post("/auth/send_totp")
async def send_login_totp(
    credentials: HTTPBasicCredentials | None = Depends(basic),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a fresh login TOTP through the user's configured email or SMS channel."""
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Basic credentials required")
    try:
        user = await authenticate_password_only(db, user_id=credentials.username, password=credentials.password)
    except ValueError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    if not user.registration_completed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account registration is not completed")
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status.HTTP_409_CONFLICT, "TOTP is not enabled for this account")
    fresh = fresh_totp_code(user.totp_secret)
    channel = user.totp_delivery_channel or "email"
    try:
        if channel == "sms":
            if not user.mobile_number or not user.mobile_verified:
                raise RuntimeError("Verified mobile number is missing")
            await send_sms(user.mobile_number, f"HGPExamWorkFlowAndChat login TOTP: {fresh['totp_code']}")
        else:
            await send_email(user.contact_email or user.email, "HGPExamWorkFlowAndChat login TOTP", f"Your login TOTP is: {fresh['totp_code']}")
    except Exception as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    await append_audit(db, user.id, "login_totp_sent", "user", user.id, details={"channel": channel})
    await db.commit()
    return {"status": "sent", "channel": channel, "expires_in_seconds": fresh["expires_in_seconds"], "valid_until": fresh["valid_until"]}


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
