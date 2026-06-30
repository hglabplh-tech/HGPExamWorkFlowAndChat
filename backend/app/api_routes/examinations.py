# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for examinations."""
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

@router.post("/examinations", status_code=201)
async def create_examination(data: ExaminationCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the create examination operation."""
    require_staff(user)
    await require_course_instructor(db, user, data.course_id)
    item = Examination(**data.model_dump(), created_by=user.id, state="draft")
    db.add(item)
    await db.commit()
    return {"id": item.id, "title": item.title, "kind": item.kind, "state": item.state}


@router.post("/examinations/draft-with-ai", status_code=201)
async def draft_examination(data: ExamDraftRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the draft examination operation."""
    require_staff(user)
    await require_course_instructor(db, user, data.course_id)
    if not await db.get(Course, data.course_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    draft = await asyncio.to_thread(create_exam_draft, data.title, data.learning_objectives, data.number_of_questions)
    item = Examination(
        course_id=data.course_id,
        title=data.title,
        kind=data.kind,
        state="draft",
        created_by=user.id,
        instructions="Instructor review is required before release.",
        generation_notes=draft,
    )
    db.add(item)
    await db.flush()
    await append_audit(db, user.id, "ai_exam_draft_created", "examination", item.id, details={"kind": item.kind, "objectives": data.learning_objectives})
    await db.commit()
    return {"id": item.id, "state": item.state, "draft": draft}


@router.post("/examinations/{examination_id}/release")
async def release_examination(
    examination_id: uuid.UUID,
    data: ExaminationRelease,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Perform the release examination operation."""
    require_staff(user)
    item = await db.get(Examination, examination_id)
    if not item or item.state != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft examination can be released")
    await require_course_instructor(db, user, item.course_id)
    question_count = await db.scalar(select(func.count()).select_from(ExamQuestion).where(ExamQuestion.examination_id == item.id))
    if not question_count:
        raise HTTPException(status.HTTP_409_CONFLICT, "Add at least one reviewed question before release")
    item.state = "released"
    item.released_at = datetime.now(UTC)
    item.closes_at = data.closes_at or item.closes_at
    await append_audit(db, user.id, "examination_released", "examination", item.id, data.reason, {"kind": item.kind, "closes_at": item.closes_at.isoformat() if item.closes_at else None})
    await db.commit()
    return {"id": item.id, "kind": item.kind, "state": item.state, "released_at": item.released_at}


@router.get("/courses/{course_id}/examinations")
async def course_examinations(course_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Perform the course examinations operation."""
    await require_course_access(db, user, course_id)
    query = select(Examination).where(Examination.course_id == course_id)
    instructor_membership = None
    if user.role == Role.teacher:
        instructor_membership = await db.scalar(select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user.id,
            Enrollment.role == Role.teacher,
        ))
    if user.role not in {Role.staff, Role.admin} and not instructor_membership:
        query = query.where(Examination.state == "released")
    examinations = (await db.scalars(query.order_by(Examination.released_at.desc().nullslast()))).all()
    output = []
    for examination in examinations:
        questions = (await db.scalars(select(ExamQuestion).where(ExamQuestion.examination_id == examination.id))).all()
        output.append({
            "id": examination.id,
            "title": examination.title,
            "kind": examination.kind,
            "state": examination.state,
            "released_at": examination.released_at,
            "closes_at": examination.closes_at,
            "questions": [{"id": question.id, "prompt": question.prompt, "max_score": question.max_score} for question in questions],
        })
    return output


@router.get("/examinations/{examination_id}/submissions")
async def examination_submissions(examination_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Perform the examination submissions operation."""
    require_staff(user)
    examination = await db.get(Examination, examination_id)
    if not examination:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examination not found")
    await require_course_instructor(db, user, examination.course_id)
    items = (await db.scalars(select(Submission).where(
        Submission.examination_id == examination_id,
        Submission.deleted_at.is_(None),
    ).order_by(Submission.submitted_at))).all()
    return [{"id": item.id, "student_id": item.student_id, "state": item.state, "submitted_at": item.submitted_at, "ai_grade": item.ai_grade, "teacher_grade": item.teacher_grade} for item in items]


@router.post("/examinations/{examination_id}/questions", status_code=201)
async def create_question(examination_id: uuid.UUID, data: QuestionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the create question operation."""
    require_staff(user)
    examination = await db.get(Examination, examination_id)
    if not examination:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examination not found")
    if examination.state != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Released examinations cannot be edited")
    await require_course_instructor(db, user, examination.course_id)
    item = ExamQuestion(examination_id=examination_id, **data.model_dump())
    db.add(item)
    await db.commit()
    return {"id": item.id, "max_score": item.max_score}
