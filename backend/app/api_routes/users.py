# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for users."""
import csv
import base64
import hashlib
import io
import json
import uuid
import asyncio
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..config import get_settings
from ..models import Conversation, ConversationMember, Course, DisciplineScoringProfile, Document, Enrollment, ExamQuestion, Examination, GradeEvent, Message, ModelTrainingRun, OCSPQuery, PrivatePKI, ResearchInteraction, Role, SignatureValidation, Submission, TrainingExample, TrustList, User, UserCertificate, VideoResource
from ..schemas import CertificateRevoke, ConversationCreate, CourseCreate, CourseOut, DeletionRequest, DocumentCreate, EmailRequest, ExamDraftRequest, ExaminationCreate, ExaminationRelease, GradeOverride, InstructorReturn, MessageCreate, PrivatePKICreate, PublicKeyUpdate, QuestionCreate, ResearchQuestionCreate, ResearchVisibilityUpdate, ScoringProfileCreate, SearchResponse, SignatureValidationRequest, SubmissionCreate, SubmissionOut, TotpVerify, TrainingApproval, TrustListCreate, TrustListDecision, UserCertificateAssign, UserCreate, UserUpdate, VideoCreate
from ..security import authenticate, generate_totp_secret, hash_password, require_nonce, totp_uri, verify_totp
from ..services.audit import append_audit
from ..services.asag import grade_answer
from ..services.evidence import certificate_matches_public_key, certificate_sha256, grading_signature_message, sha256_hex, signature_message, validate_public_key_pem, verify_certificate_signature
from ..services.indexing import index_approved_document, make_chunks
from ..services.model_router import select_models
from ..services.research import answer_research_question, create_exam_draft
from ..services.reports import generate_exam_report
from ..services.private_pki import verify_private_chain, verify_root
from ..services.ocsp import parse_ocsp_request, sign_ocsp_response
from ..services.search import hybrid_search
from ..services.trust import TrustValidator, parse_etsi_trust_list
from ..services.authorization import has_permission, validate_permissions
from ..services.email_delivery import send_email


from .common import (
    active_scoring_profile, build_grade_proposal, require_active_signing_certificate,
    require_admin, require_course_access, require_course_instructor, require_staff,
    require_training_manager, store_exam_report,
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
