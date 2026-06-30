# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for content."""
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

@router.post("/documents", status_code=201)
async def create_document(data: DocumentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the create document operation."""
    require_staff(user)
    values = data.model_dump()
    values["metadata_"] = values.pop("metadata")
    item = Document(**values)
    item.chunks = make_chunks(item)
    db.add(item)
    await db.commit()
    return {"id": item.id, "chunks": len(item.chunks), "status": "awaiting_staff_approval"}


@router.post("/documents/{document_id}/approve")
async def approve_document(
    document_id: uuid.UUID,
    background: BackgroundTasks,
    profile: str = Query(default="economy", pattern="^(economy|quality)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Perform the approve document operation."""
    require_staff(user)
    item = await db.scalar(select(Document).options(selectinload(Document.chunks)).where(Document.id == document_id))
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    item.staff_approved = True
    await db.commit()
    background.add_task(index_approved_document, item, profile)
    return {"id": item.id, "status": "approved", "indexing": "queued", "profile": profile}


@router.post("/videos", status_code=201)
async def create_video(data: VideoCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the create video operation."""
    require_staff(user)
    item = VideoResource(**data.model_dump(mode="json"))
    db.add(item)
    await db.commit()
    return {"id": item.id, "status": "awaiting_staff_approval"}


@router.post("/videos/{video_id}/approve")
async def approve_video(video_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the approve video operation."""
    require_staff(user)
    item = await db.get(VideoResource, video_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    item.staff_approved = True
    await db.commit()
    return {"id": item.id, "status": "approved"}


@router.get("/videos.csv")
async def export_videos(db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Perform the export videos operation."""
    require_staff(user)
    output = io.StringIO()
    fields = ["youtube_url", "youtube_video_id", "title", "description", "discipline", "course_id", "question_tags", "keywords", "staff_approved"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for video in (await db.scalars(select(VideoResource))).all():
        writer.writerow({name: getattr(video, name) for name in fields})
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=videos.csv"})
