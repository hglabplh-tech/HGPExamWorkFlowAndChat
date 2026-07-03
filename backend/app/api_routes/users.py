# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for users."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Role, User
from ..schemas import DeletionRequest, EmailRequest, PublicKeyUpdate, TotpVerify, UserCreate, UserUpdate
from ..security import authenticate, generate_totp_secret, hash_password, require_nonce, totp_uri, verify_totp
from ..services.audit import append_audit
from ..services.evidence import validate_public_key_pem
from ..services.authorization import has_permission, validate_permissions
from ..services.email_delivery import send_email


from .common import (
    require_admin,
)

router = APIRouter(prefix="/api/v1")


@router.post("/users/me/totp/setup")
async def setup_totp(db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Create a TOTP secret for the current account without enabling it yet."""
    secret = generate_totp_secret()
    user.totp_secret = secret
    user.totp_enabled = False
    await append_audit(db, user.id, "totp_setup_started", "user", user.id)
    await db.commit()
    return {"secret": secret, "otpauth_uri": totp_uri(secret, user.email), "enabled": False}


@router.post("/users/me/totp/verify")
async def enable_totp(data: TotpVerify, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Enable TOTP after a valid authenticator code is supplied."""
    if not user.totp_secret or not verify_totp(user.totp_secret, data.code):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid TOTP code")
    user.totp_enabled = True
    await append_audit(db, user.id, "totp_enabled", "user", user.id)
    await db.commit()
    return {"enabled": True}


@router.put("/users/me/signing-key")
async def register_signing_key(data: PublicKeyUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the register signing key operation."""
    try:
        validate_public_key_pem(data.public_key_pem.encode())
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    user.signing_public_key = data.public_key_pem.encode()
    await append_audit(db, user.id, "signing_key_registered", "user", user.id)
    await db.commit()
    return {"status": "registered"}


@router.post("/users", status_code=201)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    """Perform the create user operation."""
    require_admin(admin)
    try:
        role = Role(data.role)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown role") from error
    try:
        permissions = validate_permissions(data.permissions)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    user = User(
        email=data.email,
        display_name=data.display_name,
        matriculation_number=data.matriculation_number,
        password_hash=hash_password(data.password),
        role=role,
        permissions=permissions,
        active=False,
        registration_completed=False,
        totp_secret=generate_totp_secret(),
        totp_enabled=False,
    )
    db.add(user)
    await db.flush()
    await append_audit(db, admin.id, "user_created", "user", user.id, details={"role": role.value})
    await db.commit()
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "matriculation_number": user.matriculation_number, "role": user.role, "permissions": user.permissions}


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), admin: User = Depends(authenticate)):
    """Perform the list users operation."""
    require_admin(admin)
    users = (await db.scalars(select(User).order_by(User.email))).all()
    return [{"id": user.id, "email": user.email, "display_name": user.display_name, "matriculation_number": user.matriculation_number, "role": user.role, "permissions": user.permissions, "active": user.active} for user in users]


@router.patch("/users/{user_id}")
async def update_user(user_id: uuid.UUID, data: UserUpdate, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    """Perform the update user operation."""
    require_admin(admin)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    values = data.model_dump(exclude_none=True)
    if "permissions" in values:
        try:
            values["permissions"] = validate_permissions(values["permissions"])
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    if "role" in values:
        try:
            values["role"] = Role(values["role"])
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown role") from error
    for key, value in values.items():
        setattr(user, key, value)
    audit_values = {key: value.value if isinstance(value, Role) else value for key, value in values.items()}
    await append_audit(db, admin.id, "user_updated", "user", user.id, details=audit_values)
    await db.commit()
    return {"id": user.id, "status": "updated"}


@router.post("/notifications/email")
async def email_notification(
    data: EmailRequest,
    db: AsyncSession = Depends(get_db),
    sender: User = Depends(require_nonce),
):
    """Send an audited scoring or question-answer email to an application user."""
    recipient = await db.get(User, data.recipient_user_id)
    if not recipient or not recipient.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Active recipient not found")
    if recipient.id != sender.id and not has_permission(sender, "email.send"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email permission required")
    try:
        await send_email(recipient.email, data.subject, data.message)
    except RuntimeError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    await append_audit(db, sender.id, "email_notification_sent", "user", recipient.id, details={"kind": data.kind, "subject": data.subject})
    await db.commit()
    return {"status": "sent", "recipient_user_id": recipient.id, "kind": data.kind}


@router.delete("/users/{user_id}")
async def deactivate_user(user_id: uuid.UUID, data: DeletionRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    """Perform the deactivate user operation."""
    require_admin(admin)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.active = False
    user.deleted_at = datetime.now(UTC)
    await append_audit(db, admin.id, "user_deactivated", "user", user.id, data.reason)
    await db.commit()
    return {"id": user.id, "status": "deactivated"}
