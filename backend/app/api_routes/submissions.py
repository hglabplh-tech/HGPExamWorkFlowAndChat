# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for submissions."""
import csv
import base64
import hashlib
import io
import json
import uuid
import asyncio
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..config import get_settings
from ..models import Conversation, ConversationMember, Course, DisciplineScoringProfile, Document, Enrollment, ExamGroup, ExamQuestion, Examination, GradeEvent, Message, ModelTrainingRun, OCSPQuery, PrivatePKI, ResearchInteraction, Role, SignatureValidation, Submission, SubmissionConfirmation, TrainingExample, TrustList, User, UserCertificate, VideoResource
from ..schemas import CertificateRevoke, ConversationCreate, CourseCreate, CourseOut, DeletionRequest, DocumentCreate, ExamDraftRequest, ExaminationCreate, ExaminationRelease, GradeOverride, InstructorReturn, MessageCreate, PrivatePKICreate, PublicKeyUpdate, QuestionCreate, ResearchQuestionCreate, ResearchVisibilityUpdate, ScoringProfileCreate, SearchResponse, SignatureValidationRequest, SubmissionCreate, SubmissionOut, SubmissionPrepare, TrainingApproval, TrustListCreate, TrustListDecision, UserCertificateAssign, UserCreate, UserUpdate, VideoCreate
from ..security import authenticate, create_access_token, hash_password, require_nonce
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


from .common import (
    active_scoring_profile, build_grade_proposal, require_active_signing_certificate,
    require_admin, require_course_access, require_course_instructor, require_staff,
    require_training_manager, store_exam_report,
)

router = APIRouter(prefix="/api/v1")


@router.post("/submissions/prepare")
async def prepare_real_submission(
    data: SubmissionPrepare,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Issue a one-use confirmation after asking whether the file and work are final."""
    examination = await db.get(Examination, data.examination_id)
    if not examination or examination.kind != "real" or examination.state != "released":
        raise HTTPException(status.HTTP_409_CONFLICT, "A released real examination is required")
    await require_course_access(db, user, examination.course_id)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=get_settings().submission_correction_minutes)
    confirmation = SubmissionConfirmation(
        examination_id=examination.id,
        student_id=user.id,
        content_sha256=data.content_sha256.casefold(),
        token_sha256=sha256_hex(token.encode()),
        expires_at=expires_at,
    )
    db.add(confirmation)
    await db.commit()
    return {
        "confirmation_token": token,
        "expires_at": expires_at,
        "questions": ["Is this the correct file?", "Is the examination work ready for final submission?"],
        "correction_minutes": get_settings().submission_correction_minutes,
    }

@router.post("/submissions", response_model=SubmissionOut, status_code=201)
async def submit(
    data: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
    nonce: str = Header(alias="X-Request-Nonce"),
):
    """Perform the submit operation."""
    examination = await db.get(Examination, data.examination_id)
    if not examination or examination.state != "released":
        raise HTTPException(status.HTTP_409_CONFLICT, "Examination is not released")
    if examination.closes_at and datetime.now(UTC) > examination.closes_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Examination submission period is closed")
    await require_course_access(db, user, examination.course_id)
    exam_group = None
    if examination.group_mode:
        if not data.exam_group_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "This examination requires an exam group")
        exam_group = await db.get(ExamGroup, data.exam_group_id)
        if not exam_group or exam_group.examination_id != examination.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Exam group not found for this examination")
        if not await db.get(ConversationMember, (exam_group.conversation_id, user.id)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Exam group membership required")
        if not exam_group.certificate_pem:
            raise HTTPException(status.HTTP_409_CONFLICT, "The exam group has no X.509 submission certificate")
    elif data.exam_group_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This is not a group examination")
    elif not user.signing_public_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "Register a signing public key before submitting")
    try:
        content = data.content_bytes()
        signature = data.signature_bytes()
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid base64 evidence") from error
    now = datetime.now(UTC)
    content_hash = sha256_hex(content)
    if examination.kind == "real":
        if not data.file_confirmed or not data.ready_confirmed or not data.confirmation_token:
            raise HTTPException(status.HTTP_409_CONFLICT, "Confirm the correct file and readiness using /submissions/prepare")
        confirmation = await db.scalar(select(SubmissionConfirmation).where(
            SubmissionConfirmation.examination_id == examination.id,
            SubmissionConfirmation.student_id == user.id,
            SubmissionConfirmation.token_sha256 == sha256_hex(data.confirmation_token.encode()),
        ))
        if not confirmation or confirmation.used_at or confirmation.expires_at < now:
            raise HTTPException(status.HTTP_409_CONFLICT, "Submission confirmation is invalid or expired")
        if confirmation.content_sha256 != content_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "The confirmed file differs from the submitted file")
        confirmation.used_at = now
        if data.replaces_submission_id:
            previous = await db.get(Submission, data.replaces_submission_id)
            if not previous or previous.student_id != user.id or previous.examination_id != examination.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Previous submission not found")
            if previous.state in {"under_correction", "corrected", "returned"}:
                raise HTTPException(status.HTTP_409_CONFLICT, "Instructor correction has started; replacement is blocked")
            if not previous.correction_until or now > previous.correction_until:
                raise HTTPException(status.HTTP_409_CONFLICT, "The configurable correction period has ended")
            previous.state = "superseded"
    certificate_pem = data.signing_certificate_pem.encode()
    try:
        certificate_fingerprint = certificate_sha256(certificate_pem)
        if exam_group and certificate_fingerprint != exam_group.certificate_sha256:
            raise ValueError("Submission certificate does not match the registered exam-group certificate")
        if not exam_group and not certificate_matches_public_key(certificate_pem, user.signing_public_key):
            raise ValueError("Signing certificate does not match the registered user key")
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    if not exam_group:
        await require_active_signing_certificate(db, user, certificate_fingerprint)
    if data.content_type == "application/json":
        try:
            if json.loads(content) != data.answers:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signed JSON content does not match answers")
        except json.JSONDecodeError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signed examination content is not valid JSON") from error
    if data.signed_at.tzinfo is None or abs((now - data.signed_at.astimezone(UTC)).total_seconds()) > get_settings().signature_clock_skew_seconds:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signing timestamp is outside the permitted clock window")
    message = signature_message(data.examination_id, user.id, content_hash, data.signed_at, nonce, certificate_fingerprint)
    try:
        signature_algorithm = verify_certificate_signature(certificate_pem, signature, message)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    try:
        retention_until = now.replace(year=now.year + get_settings().retention_years)
    except ValueError:
        retention_until = now.replace(month=2, day=28, year=now.year + get_settings().retention_years)
    item = Submission(
        examination_id=data.examination_id,
        student_id=user.id,
        answers=data.answers,
        content=content,
        content_type=data.content_type,
        content_sha256=content_hash,
        student_signature=signature,
        student_certificate_pem=certificate_pem,
        signature_algorithm=signature_algorithm,
        client_signed_at=data.signed_at,
        receipt_nonce=nonce,
        retention_until=retention_until,
        submitted_at=now,
        state="submitted",
        correction_until=now + timedelta(minutes=get_settings().submission_correction_minutes) if examination.kind == "real" else None,
        supersedes_submission_id=data.replaces_submission_id,
        exam_group_id=exam_group.id if exam_group else None,
        group_certificate_pem=certificate_pem if exam_group else None,
    )
    db.add(item)
    await db.flush()
    if examination.kind == "practice":
        proposal = await build_grade_proposal(db, item)
        item.ai_grade = proposal
        item.grading_sha256 = sha256_hex(json.dumps(proposal, sort_keys=True, separators=(",", ":")).encode())
        item.state = "practice_feedback_released"
        item.feedback_released_at = now
        db.add(GradeEvent(submission_id=item.id, actor_id=user.id, kind="practice_ai_feedback", grade=proposal, reason="Immediate practice feedback"))
        await store_exam_report(db, item, examination)
    else:
        item.state = "awaiting_grading"
    await append_audit(db, user.id, "examination_submitted", "submission", item.id, details={
        "sha256": content_hash,
        "student_certificate_sha256": certificate_fingerprint,
        "student_signature_sha256": sha256_hex(signature),
        "report_sha256": item.report_sha256,
        "retention_until": retention_until.isoformat(),
    })
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/submissions/{submission_id}")
async def delete_submission(submission_id: uuid.UUID, data: DeletionRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    """Perform the delete submission operation."""
    require_admin(admin)
    item = await db.get(Submission, submission_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    if datetime.now(UTC) < item.retention_until and not data.override_retention:
        raise HTTPException(status.HTTP_409_CONFLICT, "Retention period is active; an explicit override is required")
    if item.legal_hold:
        raise HTTPException(status.HTTP_409_CONFLICT, "Legal hold must be formally released before deletion")
    item.deleted_at = datetime.now(UTC)
    item.deleted_by = admin.id
    item.deletion_reason = data.reason
    await append_audit(db, admin.id, "submission_soft_deleted", "submission", item.id, data.reason, {"retention_override": data.override_retention, "legal_hold": item.legal_hold})
    await db.commit()
    return {"id": item.id, "status": "logically_deleted", "evidence_preserved": True}


@router.post("/submissions/{submission_id}/legal-hold")
async def set_legal_hold(submission_id: uuid.UUID, data: DeletionRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    """Perform the set legal hold operation."""
    require_admin(admin)
    item = await db.get(Submission, submission_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    item.legal_hold = True
    await append_audit(db, admin.id, "legal_hold_set", "submission", item.id, data.reason)
    await db.commit()
    return {"id": item.id, "legal_hold": True}


@router.post("/submissions/{submission_id}/release-legal-hold")
async def release_legal_hold(submission_id: uuid.UUID, data: DeletionRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    """Perform the release legal hold operation."""
    require_admin(admin)
    item = await db.get(Submission, submission_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    item.legal_hold = False
    await append_audit(db, admin.id, "legal_hold_released", "submission", item.id, data.reason)
    await db.commit()
    return {"id": item.id, "legal_hold": False}
