# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for research."""
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

@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=2, max_length=500),
    course_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """Perform the search operation."""
    if course_id and user.role not in {Role.staff, Role.admin}:
        membership = await db.scalar(select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user.id,
        ))
        if not membership:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Course enrollment required")
    scoring_profile = None
    if course_id:
        course = await db.get(Course, course_id)
        if course:
            scoring_profile = await db.scalar(select(DisciplineScoringProfile).where(
                DisciplineScoringProfile.discipline == course.discipline,
                DisciplineScoringProfile.active.is_(True),
            ).order_by(DisciplineScoringProfile.version.desc()))
    return await hybrid_search(
        db,
        q,
        course_id,
        profile=scoring_profile.semantic_profile if scoring_profile else "economy",
        weights=scoring_profile.search_weights if scoring_profile else None,
    )


@router.get("/search/model-decision")
async def model_decision(q: str = Query(min_length=2), profile: str | None = None, device: str | None = None, _: User = Depends(authenticate)):
    """Perform the model decision operation."""
    return select_models(q, profile, device).__dict__


@router.post("/research/questions", status_code=201)
async def ask_research_question(
    data: ResearchQuestionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Perform the ask research question operation."""
    await require_course_access(db, user, data.course_id)
    if data.visibility == "conversation":
        if not data.conversation_id or not await db.get(ConversationMember, (data.conversation_id, user.id)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Conversation membership required")
    course = await db.get(Course, data.course_id)
    if not course:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    profile = await active_scoring_profile(db, course)
    answer, sources = await answer_research_question(
        db,
        course.id,
        data.question,
        profile.semantic_profile if profile else "economy",
        profile.search_weights if profile else None,
    )
    interaction = ResearchInteraction(
        course_id=course.id,
        user_id=user.id,
        conversation_id=data.conversation_id if data.visibility == "conversation" else None,
        question=data.question,
        answer=answer,
        sources=sources,
        visibility=data.visibility,
        training_opt_in=data.training_opt_in,
    )
    db.add(interaction)
    await db.flush()
    await append_audit(db, user.id, "research_question_answered", "research_interaction", interaction.id, details={"visibility": interaction.visibility, "training_opt_in": interaction.training_opt_in})
    await db.commit()
    return {"id": interaction.id, "question": interaction.question, "answer": answer, "sources": sources, "visibility": interaction.visibility}


@router.patch("/research/{interaction_id}/visibility")
async def update_research_visibility(
    interaction_id: uuid.UUID,
    data: ResearchVisibilityUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Perform the update research visibility operation."""
    item = await db.get(ResearchInteraction, interaction_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research interaction not found")
    if data.visibility == "conversation":
        if not data.conversation_id or not await db.get(ConversationMember, (data.conversation_id, user.id)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Conversation membership required")
    item.visibility = data.visibility
    item.conversation_id = data.conversation_id if data.visibility == "conversation" else None
    item.training_opt_in = data.training_opt_in
    await append_audit(db, user.id, "research_visibility_changed", "research_interaction", item.id, details={"visibility": item.visibility, "training_opt_in": item.training_opt_in})
    await db.commit()
    return {"id": item.id, "visibility": item.visibility, "training_opt_in": item.training_opt_in}


@router.get("/research/history")
async def research_history(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """Perform the research history operation."""
    await require_course_access(db, user, course_id)
    conversation_ids = select(ConversationMember.conversation_id).where(ConversationMember.user_id == user.id)
    items = (await db.scalars(select(ResearchInteraction).where(
        ResearchInteraction.course_id == course_id,
        or_(
            ResearchInteraction.user_id == user.id,
            ResearchInteraction.visibility == "course",
            and_(ResearchInteraction.visibility == "conversation", ResearchInteraction.conversation_id.in_(conversation_ids)),
        ),
    ).order_by(ResearchInteraction.created_at.desc()).limit(200))).all()
    return [{"id": item.id, "question": item.question, "answer": item.answer, "sources": item.sources, "visibility": item.visibility, "owner": item.user_id == user.id, "created_at": item.created_at} for item in items]


@router.get("/coverage")
async def coverage(db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Perform the coverage operation."""
    require_staff(user)
    courses = (await db.scalars(select(Course).order_by(Course.code))).all()
    documents = (await db.scalars(select(Document).where(Document.staff_approved.is_(True)))).all()
    videos = (await db.scalars(select(VideoResource).where(VideoResource.staff_approved.is_(True)))).all()
    return [
        {
            "course_id": course.id,
            "code": course.code,
            "title": course.title,
            "approved_documents": sum(item.course_id in {None, course.id} for item in documents),
            "approved_videos": sum(item.course_id in {None, course.id} for item in videos),
        }
        for course in courses
    ]
