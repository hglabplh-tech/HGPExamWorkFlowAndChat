# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for grading."""
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
from ..schemas import CertificateRevoke, ConversationCreate, CourseCreate, CourseOut, DeletionRequest, DocumentCreate, ExamDraftRequest, ExaminationCreate, ExaminationRelease, GradeOverride, InstructorReturn, MessageCreate, PrivatePKICreate, PublicKeyUpdate, QuestionCreate, ResearchQuestionCreate, ResearchVisibilityUpdate, ScoringProfileCreate, SearchResponse, SignatureValidationRequest, SubmissionCreate, SubmissionOut, TrainingApproval, TrustListCreate, TrustListDecision, UserCertificateAssign, UserCreate, UserUpdate, VideoCreate
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

@router.get("/submissions/{submission_id}")
async def get_submission(submission_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Perform the get submission operation."""
    item = await db.get(Submission, submission_id)
    if not item or item.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    if item.student_id != user.id and user.role not in {Role.teacher, Role.staff, Role.admin}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Submission access denied")
    examination = await db.get(Examination, item.examination_id)
    if item.student_id != user.id and user.role == Role.teacher:
        await require_course_instructor(db, user, examination.course_id)
    may_see_feedback = user.role in {Role.teacher, Role.staff, Role.admin} or examination.kind == "practice" or item.state == "returned"
    return {
        "id": item.id,
        "examination_id": item.examination_id,
        "state": item.state,
        "answers": item.answers,
        "ai_grade": item.ai_grade if may_see_feedback else None,
        "teacher_grade": item.teacher_grade if may_see_feedback else None,
        "submitted_at": item.submitted_at,
        "returned_at": item.returned_at,
        "report_sha256": item.report_sha256 if may_see_feedback else None,
    }


@router.get("/submissions/{submission_id}/report.pdf")
async def examination_report(submission_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Perform the examination report operation."""
    item = await db.get(Submission, submission_id)
    if not item or item.deleted_at or not item.report_pdf:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examination report not found")
    examination = await db.get(Examination, item.examination_id)
    if item.student_id != user.id:
        if user.role not in {Role.teacher, Role.staff, Role.admin}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Report access denied")
        if user.role == Role.teacher:
            await require_course_instructor(db, user, examination.course_id)
    if item.student_id == user.id and examination.kind == "real" and item.state != "returned":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Real-exam report has not been returned")
    filename = f"examination-report-{item.id}.pdf"
    return Response(
        item.report_pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Report-SHA256": item.report_sha256 or "",
        },
    )


@router.post("/submissions/{submission_id}/ai-grade")
async def propose_ai_grade(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Perform the propose ai grade operation."""
    require_staff(user)
    submission = await db.get(Submission, submission_id)
    if not submission or submission.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    examination = await db.get(Examination, submission.examination_id)
    await require_course_instructor(db, user, examination.course_id)
    if examination.kind == "practice" and submission.report_pdf:
        raise HTTPException(status.HTTP_409_CONFLICT, "Practice feedback and report are already final")
    proposal = await build_grade_proposal(db, submission)
    submission.ai_grade = proposal
    db.add(GradeEvent(submission_id=submission.id, actor_id=user.id, kind="ai_proposal", grade=proposal, reason="Weighted ASAG scoring"))
    await append_audit(db, user.id, "ai_grade_proposed", "submission", submission.id, details={"profile_id": proposal["profile_id"], "total": proposal["total"], "requires_teacher_review": proposal["requires_teacher_review"]})
    await db.commit()
    return proposal


@router.post("/submissions/{submission_id}/teacher-override")
async def override_grade(
    submission_id: uuid.UUID,
    data: GradeOverride,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Perform the override grade operation."""
    require_staff(user)
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    examination = await db.get(Examination, submission.examination_id)
    await require_course_instructor(db, user, examination.course_id)
    grade = data.model_dump(exclude={"reason"})
    submission.teacher_grade = grade
    submission.state = "corrected"
    db.add(GradeEvent(submission_id=submission.id, actor_id=user.id, kind="teacher_override", grade=grade, reason=data.reason))
    await append_audit(db, user.id, "teacher_grade_override", "submission", submission.id, data.reason, {"grade": grade})
    await db.commit()
    return {"submission_id": submission.id, "effective_grade": grade, "overridden_by": user.id}


@router.post("/submissions/{submission_id}/return")
async def return_graded_submission(
    submission_id: uuid.UUID,
    data: InstructorReturn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Perform the return graded submission operation."""
    require_staff(user)
    submission = await db.get(Submission, submission_id)
    if not submission or submission.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    examination = await db.get(Examination, submission.examination_id)
    await require_course_instructor(db, user, examination.course_id)
    if examination.kind != "real":
        raise HTTPException(status.HTTP_409_CONFLICT, "Practice examinations already return AI-only reports")
    if not submission.teacher_grade:
        raise HTTPException(status.HTTP_409_CONFLICT, "Teacher-approved grading is required before return")
    if not user.signing_public_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "Instructor must register a signing key before return")
    if data.signed_at.tzinfo is None or abs((datetime.now(UTC) - data.signed_at.astimezone(UTC)).total_seconds()) > get_settings().signature_clock_skew_seconds:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Instructor signing timestamp is outside the permitted clock window")
    certificate_pem = data.signing_certificate_pem.encode()
    try:
        certificate_fingerprint = certificate_sha256(certificate_pem)
        if not certificate_matches_public_key(certificate_pem, user.signing_public_key):
            raise ValueError("Instructor certificate does not match the registered user key")
        grading_hash = sha256_hex(json.dumps(submission.teacher_grade, sort_keys=True, separators=(",", ":")).encode())
        message = grading_signature_message(
            submission.id,
            submission.content_sha256,
            sha256_hex(submission.student_signature),
            grading_hash,
            data.signed_at,
            certificate_fingerprint,
        )
        instructor_signature = base64.b64decode(data.signature_base64, validate=True)
        verify_certificate_signature(certificate_pem, instructor_signature, message)
    except (ValueError, TypeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await require_active_signing_certificate(db, user, certificate_fingerprint)
    submission.grading_sha256 = grading_hash
    submission.instructor_signature = instructor_signature
    submission.instructor_certificate_pem = certificate_pem
    submission.instructor_signed_at = data.signed_at
    submission.state = "returned"
    submission.returned_at = datetime.now(UTC)
    submission.feedback_released_at = submission.returned_at
    await store_exam_report(db, submission, examination)
    await append_audit(db, user.id, "graded_submission_returned", "submission", submission.id, details={
        "student_id": str(submission.student_id),
        "grading_sha256": submission.grading_sha256,
        "instructor_certificate_sha256": certificate_fingerprint,
        "instructor_signature_sha256": sha256_hex(instructor_signature),
        "report_sha256": submission.report_sha256,
    })
    await db.commit()
    return {"submission_id": submission.id, "state": submission.state, "returned_at": submission.returned_at}
