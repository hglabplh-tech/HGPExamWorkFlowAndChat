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
from ..models import ActiveUserSession, Conversation, ConversationMember, Course, DisciplineScoringProfile, Document, Enrollment, ExamQuestion, Examination, GradeEvent, Message, ModelTrainingRun, OCSPQuery, PrivatePKI, ResearchHistory, ResearchHistoryEntry, ResearchInteraction, Role, SignatureValidation, Submission, Thesaurus, TrainingExample, TrustList, User, UserCertificate, VideoResource
from ..schemas import CertificateRevoke, ConversationCreate, CourseCreate, CourseOut, DeletionRequest, DocumentCreate, ExamDraftRequest, ExaminationCreate, ExaminationRelease, GradeOverride, InstructorReturn, MessageCreate, PrivatePKICreate, PublicKeyUpdate, QuestionCreate, ResearchHistoryCreate, ResearchHistoryUpdate, ResearchQuestionCreate, ResearchVisibilityUpdate, ScoringProfileCreate, SearchResponse, SignatureValidationRequest, SubmissionCreate, SubmissionOut, TrainingApproval, TrustListCreate, TrustListDecision, UserCertificateAssign, UserCreate, UserUpdate, VideoCreate
from ..security import authenticate, create_access_token, current_active_session, hash_password, require_nonce
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
from ..services.research_history import current_or_create_history, recent_entries, record_history_entry, refine_query_with_history, summarize_hits
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
    use_thesaurus: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
    session: ActiveUserSession | None = Depends(current_active_session),
):
    """Perform hybrid search and refine it with the user's recent research history."""
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
    thesaurus_entries: list[dict] = []
    if use_thesaurus:
        thesauri = (await db.scalars(select(Thesaurus).where(Thesaurus.active.is_(True)))).all()
        for thesaurus in thesauri:
            thesaurus_entries.extend(thesaurus.entries)
    history = await current_or_create_history(db, user, session)
    refined_q = refine_query_with_history(q, await recent_entries(db, history))
    response = await hybrid_search(
        db,
        refined_q,
        course_id,
        profile=scoring_profile.semantic_profile if scoring_profile else "economy",
        weights=scoring_profile.search_weights if scoring_profile else None,
        thesaurus_entries=thesaurus_entries,
    )
    response.query = q
    response.query_expansion = {
        **(response.query_expansion or {}),
        "history_refined_query": refined_q,
        "history_id": str(history.id),
    }
    await record_history_entry(
        db,
        user=user,
        session=session,
        kind="hybrid_search",
        input_text=q,
        refined_text=refined_q,
        course_id=course_id,
        output_summary=summarize_hits(response.results),
        payload={"result_count": len(response.results), "use_thesaurus": use_thesaurus},
    )
    await db.commit()
    return response


@router.get("/search/model-decision")
async def model_decision(q: str = Query(min_length=2), profile: str | None = None, device: str | None = None, _: User = Depends(authenticate)):
    """Perform the model decision operation."""
    return select_models(q, profile, device).__dict__


@router.post("/research/questions", status_code=201)
async def ask_research_question(
    data: ResearchQuestionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
    session: ActiveUserSession | None = Depends(current_active_session),
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
    thesaurus_entries: list[dict] = []
    thesauri = (await db.scalars(select(Thesaurus).where(Thesaurus.active.is_(True)))).all()
    for thesaurus in thesauri:
        thesaurus_entries.extend(thesaurus.entries)
    answer, sources = await answer_research_question(
        db,
        course.id,
        data.question,
        profile.semantic_profile if profile else "economy",
        profile.search_weights if profile else None,
        thesaurus_entries,
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
    await record_history_entry(
        db,
        user=user,
        session=session,
        kind="research_question",
        input_text=data.question,
        course_id=course.id,
        output_summary=answer,
        payload={"interaction_id": str(interaction.id), "source_count": len(sources), "visibility": interaction.visibility},
    )
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


@router.get("/research/histories")
async def list_research_histories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
    session: ActiveUserSession | None = Depends(current_active_session),
):
    """List the current user's non-deleted research histories."""
    if session:
        await current_or_create_history(db, user, session)
        await db.commit()
    items = (await db.scalars(select(ResearchHistory).where(
        ResearchHistory.user_id == user.id,
        ResearchHistory.deleted_at.is_(None),
    ).order_by(ResearchHistory.updated_at.desc()).limit(100))).all()
    counts = {
        row[0]: row[1] for row in (await db.execute(
            select(ResearchHistoryEntry.history_id, func.count(ResearchHistoryEntry.id)).where(
                ResearchHistoryEntry.history_id.in_([item.id for item in items] or [uuid.uuid4()])
            ).group_by(ResearchHistoryEntry.history_id)
        )).all()
    }
    return [{
        "id": item.id,
        "label": item.label,
        "stored": item.stored,
        "active": bool(session and item.active_session_id == session.id and not item.stored),
        "entries": counts.get(item.id, 0),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    } for item in items]


@router.post("/research/histories", status_code=201)
async def create_research_history(
    data: ResearchHistoryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
    session: ActiveUserSession | None = Depends(current_active_session),
):
    """Create and activate a new research history, equivalent to 'New chat'."""
    if session:
        existing = (await db.scalars(select(ResearchHistory).where(
            ResearchHistory.user_id == user.id,
            ResearchHistory.active_session_id == session.id,
            ResearchHistory.deleted_at.is_(None),
            ResearchHistory.stored.is_(False),
        ))).all()
        for item in existing:
            item.stored = True
            item.updated_at = datetime.now(UTC)
    history = ResearchHistory(user_id=user.id, active_session_id=session.id if session else None, label=data.label)
    db.add(history)
    await db.flush()
    await append_audit(db, user.id, "research_history_created", "research_history", history.id, details={"label": history.label})
    await db.commit()
    return {"id": history.id, "label": history.label, "stored": history.stored, "active": True}


@router.post("/research/histories/{history_id}/activate")
async def activate_research_history(
    history_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
    session: ActiveUserSession | None = Depends(current_active_session),
):
    """Make one stored history the active context for the current login session."""
    history = await db.get(ResearchHistory, history_id)
    if not history or history.user_id != user.id or history.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research history not found")
    if session:
        previous = (await db.scalars(select(ResearchHistory).where(
            ResearchHistory.user_id == user.id,
            ResearchHistory.active_session_id == session.id,
            ResearchHistory.deleted_at.is_(None),
            ResearchHistory.stored.is_(False),
            ResearchHistory.id != history.id,
        ))).all()
        for item in previous:
            item.stored = True
            item.updated_at = datetime.now(UTC)
        history.active_session_id = session.id
    history.stored = False
    history.updated_at = datetime.now(UTC)
    await append_audit(db, user.id, "research_history_activated", "research_history", history.id)
    await db.commit()
    return {"id": history.id, "label": history.label, "active": True}


@router.patch("/research/histories/{history_id}")
async def update_research_history(
    history_id: uuid.UUID,
    data: ResearchHistoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Rename or store one of the user's research histories."""
    history = await db.get(ResearchHistory, history_id)
    if not history or history.user_id != user.id or history.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research history not found")
    if data.label is not None:
        history.label = data.label
    if data.stored is not None:
        history.stored = data.stored
    history.updated_at = datetime.now(UTC)
    await append_audit(db, user.id, "research_history_updated", "research_history", history.id, details=data.model_dump(exclude_none=True))
    await db.commit()
    return {"id": history.id, "label": history.label, "stored": history.stored}


@router.delete("/research/histories/{history_id}")
async def delete_research_history(
    history_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Soft-delete one of the user's research histories."""
    history = await db.get(ResearchHistory, history_id)
    if not history or history.user_id != user.id or history.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research history not found")
    history.deleted_at = datetime.now(UTC)
    history.updated_at = history.deleted_at
    await append_audit(db, user.id, "research_history_deleted", "research_history", history.id)
    await db.commit()
    return {"id": history.id, "deleted": True}


@router.get("/research/histories/{history_id}/entries")
async def list_research_history_entries(
    history_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """List entries inside one of the user's research histories."""
    history = await db.get(ResearchHistory, history_id)
    if not history or history.user_id != user.id or history.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research history not found")
    entries = (await db.scalars(select(ResearchHistoryEntry).where(
        ResearchHistoryEntry.history_id == history.id,
    ).order_by(ResearchHistoryEntry.created_at.desc()).limit(200))).all()
    return [{
        "id": entry.id,
        "kind": entry.kind,
        "label": entry.label,
        "input_text": entry.input_text,
        "refined_text": entry.refined_text,
        "output_summary": entry.output_summary,
        "payload": entry.payload,
        "created_at": entry.created_at,
    } for entry in entries]


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
