# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for chat."""
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

@router.post("/conversations", status_code=201)
async def create_conversation(data: ConversationCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the create conversation operation."""
    members = set(data.member_ids) | {user.id}
    if data.kind == "direct" and len(members) != 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A direct conversation must have exactly two members")
    enrolled = set(await db.scalars(select(Enrollment.user_id).where(
        Enrollment.course_id == data.course_id,
        Enrollment.user_id.in_(members),
    )))
    if enrolled != members and user.role not in {Role.staff, Role.admin}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Every conversation member must be enrolled in the course")
    conversation = Conversation(course_id=data.course_id, title=data.title, kind=data.kind, created_by=user.id)
    db.add(conversation)
    await db.flush()
    db.add_all(ConversationMember(conversation_id=conversation.id, user_id=member) for member in members)
    await append_audit(db, user.id, "conversation_created", "conversation", conversation.id, details={"members": [str(member) for member in members]})
    await db.commit()
    return {"id": conversation.id, "members": len(members)}


async def validate_chat_share(db: AsyncSession, user: User, conversation_id: uuid.UUID, shared_type: str | None, shared_id: uuid.UUID | None) -> None:
    """Perform the validate chat share operation."""
    if not shared_type:
        return
    if not shared_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Shared resource ID is required")
    if shared_type == "research_result":
        item = await db.get(ResearchInteraction, shared_id)
        if not item or item.user_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only your own research result can be shared")
        item.visibility = "conversation"
        item.conversation_id = conversation_id
    elif shared_type == "practice_score":
        submission = await db.get(Submission, shared_id)
        examination = await db.get(Examination, submission.examination_id) if submission else None
        if not submission or submission.student_id != user.id or not examination or examination.kind != "practice" or not submission.ai_grade:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only your own scored practice examination can be shared")
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported shared resource type")


@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def post_message(
    conversation_id: uuid.UUID,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Perform the post message operation."""
    if not await db.get(ConversationMember, (conversation_id, user.id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Conversation membership required")
    await validate_chat_share(db, user, conversation_id, data.shared_type, data.shared_id)
    item = Message(conversation_id=conversation_id, sender_id=user.id, **data.model_dump())
    db.add(item)
    await db.commit()
    return {"id": item.id, "created_at": item.created_at}


@router.get("/conversations/{conversation_id}/messages")
async def conversation_messages(
    conversation_id: uuid.UUID,
    before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """Perform the conversation messages operation."""
    if not await db.get(ConversationMember, (conversation_id, user.id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Conversation membership required")
    query = select(Message).where(Message.conversation_id == conversation_id)
    if before:
        query = query.where(Message.created_at < before)
    items = (await db.scalars(query.order_by(Message.created_at.desc()).limit(limit))).all()
    return [{"id": item.id, "sender_id": item.sender_id, "body": item.body, "shared_type": item.shared_type, "shared_id": item.shared_id, "created_at": item.created_at} for item in reversed(items)]


@router.get("/conversations/{conversation_id}/shared-submissions/{submission_id}")
async def shared_submission(
    conversation_id: uuid.UUID,
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """Perform the shared submission operation."""
    member = await db.get(ConversationMember, (conversation_id, user.id))
    if not member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Conversation membership required")
    share = await db.scalar(select(Message).where(
        Message.conversation_id == conversation_id,
        Message.shared_type == "practice_score",
        Message.shared_id == submission_id,
    ))
    if not share:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission was not shared in this conversation")
    item = await db.get(Submission, submission_id)
    if not item or item.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    examination = await db.get(Examination, item.examination_id)
    if item.student_id != user.id and user.role == Role.teacher:
        await require_course_instructor(db, user, examination.course_id)
    if not examination or examination.kind != "practice" or not item.ai_grade:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only practice-exam feedback may be shared")
    return {"id": item.id, "answers": item.answers, "ai_grade": item.ai_grade, "teacher_grade": item.teacher_grade}


@router.get("/conversations/{conversation_id}/shared-research/{interaction_id}")
async def shared_research(
    conversation_id: uuid.UUID,
    interaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """Perform the shared research operation."""
    if not await db.get(ConversationMember, (conversation_id, user.id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Conversation membership required")
    share = await db.scalar(select(Message).where(
        Message.conversation_id == conversation_id,
        Message.shared_type == "research_result",
        Message.shared_id == interaction_id,
    ))
    item = await db.get(ResearchInteraction, interaction_id)
    if not share or not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research result was not shared in this conversation")
    return {"id": item.id, "question": item.question, "answer": item.answer, "sources": item.sources}
