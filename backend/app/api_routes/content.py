# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for content."""
import csv
import hashlib
import io
import json
import uuid
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..config import get_settings
from ..models import Document, Thesaurus, TrainingExample, User, VideoResource
from ..schemas import DocumentCreate, ThesaurusJsonImport, ThesaurusOut, VideoCreate
from ..security import authenticate, require_nonce
from ..services.audit import append_audit
from ..services.academic_integrity import fact_check_knowledge_text
from ..services.evidence import sha256_hex
from ..services.indexing import index_approved_document, make_chunks, rebuild_chroma_from_documents
from ..services.audio import transcribe_audio
from ..services.ingestion import ContentExtractor, KnowledgeImporter, answer_from_uploaded_text
from ..services.thesaurus import parse_thesaurus_payload
from ..services.vocabulary import build_vocabulary_bundle, vocabulary_text


from .common import (
    require_admin, require_staff,
)

router = APIRouter(prefix="/api/v1")


@router.post("/thesauri/upload", response_model=ThesaurusOut, status_code=201)
async def upload_thesaurus(
    file: UploadFile = File(...),
    name: str = Form(..., min_length=2, max_length=120),
    language: str = Form(default="simple", max_length=20),
    source_format: str = Form(default="solr_synonyms"),
    active: bool = Form(default=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Import a Solr-style text thesaurus or normalized JSON thesaurus."""
    require_staff(user)
    payload = await file.read()
    try:
        entries = parse_thesaurus_payload(payload, source_format)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    if not entries:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Thesaurus contains no usable entries")
    digest = hashlib.sha256(payload).hexdigest()
    item = await db.scalar(select(Thesaurus).where(Thesaurus.source_sha256 == digest))
    if not item:
        item = Thesaurus(
            name=name, language=language, source_format=source_format,
            entries=entries, source_sha256=digest, active=active, created_by=user.id,
        )
        db.add(item)
    else:
        item.name = name
        item.language = language
        item.source_format = source_format
        item.entries = entries
        item.active = active
    await db.flush()
    await append_audit(db, user.id, "thesaurus_imported", "thesaurus", item.id, details={"entries": len(entries), "language": language})
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/thesauri", response_model=ThesaurusOut, status_code=201)
async def create_thesaurus_from_json(
    data: ThesaurusJsonImport,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Create a thesaurus directly from normalized JSON entries."""
    require_staff(user)
    payload = json.dumps(data.entries, sort_keys=True).encode("utf-8")
    entries = parse_thesaurus_payload(payload, "json")
    if not entries:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Thesaurus contains no usable entries")
    digest = hashlib.sha256(payload).hexdigest()
    item = await db.scalar(select(Thesaurus).where(Thesaurus.source_sha256 == digest))
    if not item:
        item = Thesaurus(
            name=data.name, language=data.language, source_format="json",
            entries=entries, source_sha256=digest, active=data.active, created_by=user.id,
        )
        db.add(item)
    else:
        item.name = data.name
        item.language = data.language
        item.entries = entries
        item.active = data.active
    await db.flush()
    await append_audit(db, user.id, "thesaurus_created", "thesaurus", item.id, details={"entries": len(entries), "language": data.language})
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/thesauri", response_model=list[ThesaurusOut])
async def list_thesauri(db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """List thesauri available for full-text expansion."""
    require_staff(user)
    return (await db.scalars(select(Thesaurus).order_by(Thesaurus.name, Thesaurus.language))).all()


@router.get("/thesauri/{thesaurus_id}.json")
async def export_thesaurus_json(thesaurus_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Export one thesaurus in normalized JSON format."""
    require_staff(user)
    item = await db.get(Thesaurus, thesaurus_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thesaurus not found")
    return {"name": item.name, "language": item.language, "entries": item.entries, "active": item.active}

@router.post("/documents", status_code=201)
async def create_document(data: DocumentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the create document operation."""
    require_staff(user)
    values = data.model_dump()
    values["metadata_"] = values.pop("metadata")
    values["content_sha256"] = sha256_hex(values["body_text"].encode())
    existing = await db.scalar(select(Document).where(Document.content_sha256 == values["content_sha256"]))
    if existing:
        return {"id": existing.id, "status": "duplicate_unchanged"}
    item = Document(**values)
    item.chunks = make_chunks(item)
    db.add(item)
    await db.commit()
    return {"id": item.id, "chunks": len(item.chunks), "status": "awaiting_staff_approval"}


@router.post("/knowledge/upload", status_code=201)
async def upload_knowledge(
    file: UploadFile = File(...),
    title: str = Form(...),
    course_id: uuid.UUID | None = Form(default=None),
    source_uri: str | None = Form(default=None),
    approve: bool = Form(default=False),
    fact_check: bool = Form(default=True),
    rubric: str = Form(default="general"),
    topic: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Import one PDF/text file idempotently into PostgreSQL."""
    require_staff(user)
    try:
        extracted = await asyncio.to_thread(ContentExtractor.extract, await file.read(), file.content_type or "application/octet-stream", file.filename or "")
        fact_review = await fact_check_knowledge_text(extracted.text, rubric=rubric, topic=topic) if fact_check else {"status": "disabled", "decision": "not_checked"}
        if fact_review.get("status") == "completed" and fact_review.get("decision") != "accepted" and approve:
            raise ValueError("Trusted-source fact check requires manual review before approval")
        item, created = await KnowledgeImporter.import_document(
            db, title=title, content=extracted, course_id=course_id,
            source_uri=source_uri, metadata={"filename": file.filename, "fact_check": fact_review}, approve=approve and fact_review.get("decision") == "accepted",
        )
    except (ValueError, UnicodeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await append_audit(db, user.id, "knowledge_imported" if created else "knowledge_duplicate_skipped", "document", item.id, details={"sha256": extracted.sha256})
    await db.commit()
    return {"id": item.id, "created": created, "sha256": extracted.sha256, "fact_check": fact_review, "status": "inserted" if created else "duplicate_unchanged"}


@router.post("/knowledge/upload-and-ask", status_code=201)
async def upload_and_ask(
    file: UploadFile = File(...),
    question: str = Form(..., min_length=2, max_length=4000),
    title: str = Form(...),
    course_id: uuid.UUID | None = Form(default=None),
    import_to_knowledge: bool = Form(default=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Accept a file and question in one HTTP RPC request and optionally persist it."""
    try:
        extracted = await asyncio.to_thread(ContentExtractor.extract, await file.read(), file.content_type or "application/octet-stream", file.filename or "")
    except (ValueError, UnicodeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    document_id = None
    created = False
    if import_to_knowledge:
        require_staff(user)
        document, created = await KnowledgeImporter.import_document(
            db, title=title, content=extracted, course_id=course_id,
            source_uri=None, metadata={"filename": file.filename, "question": question}, approve=False,
        )
        document_id = document.id
        await db.commit()
    return {"document_id": document_id, "created": created, "sha256": extracted.sha256, **answer_from_uploaded_text(question, extracted.text)}


@router.get("/knowledge/export.json")
async def export_knowledge(db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Export PostgreSQL courses and knowledge as a versioned JSON bundle."""
    require_staff(user)
    return await KnowledgeImporter.export_bundle(db)


@router.post("/knowledge/rebuild-chroma")
async def rebuild_chroma_index(
    profile: str = Query(default="economy", pattern="^(economy|quality)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Rebuild the derived ChromaDB vector index from approved PostgreSQL documents."""
    require_admin(user)
    documents = (await db.scalars(select(Document).options(selectinload(Document.chunks)).where(
        Document.staff_approved.is_(True),
    ).order_by(Document.title))).all()
    created_chunks = 0
    for document in documents:
        if not document.chunks:
            document.chunks = make_chunks(document)
            created_chunks += len(document.chunks)
    if created_chunks:
        await db.flush()
    result = await asyncio.to_thread(rebuild_chroma_from_documents, list(documents), profile)
    await append_audit(db, user.id, "chroma_rebuilt", "knowledge", user.id, details={**result, "created_chunks": created_chunks})
    await db.commit()
    return {**result, "created_chunks": created_chunks}


@router.get("/knowledge/vocabulary.json")
async def export_vocabulary_json(
    min_frequency: int = Query(default=1, ge=1, le=1000),
    limit: int = Query(default=50000, ge=1, le=200000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """Export a generated JSON vocabulary from approved knowledge documents."""
    require_staff(user)
    return await build_vocabulary_bundle(db, min_frequency=min_frequency, limit=limit)


@router.get("/knowledge/vocab.txt")
async def export_vocabulary_text(
    min_frequency: int = Query(default=1, ge=1, le=1000),
    limit: int = Query(default=50000, ge=1, le=200000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """Export a one-token-per-line vocabulary file for local model training."""
    require_staff(user)
    bundle = await build_vocabulary_bundle(db, min_frequency=min_frequency, limit=limit)
    return Response(vocabulary_text(bundle), media_type="text/plain", headers={"Content-Disposition": "attachment; filename=vocab.txt"})


@router.post("/knowledge/import-bundle")
async def import_knowledge_bundle(
    file: UploadFile = File(...),
    fact_check: bool = Form(default=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Idempotently merge a previously exported knowledge bundle."""
    require_staff(user)
    try:
        result = await KnowledgeImporter.import_bundle(db, await file.read(), fact_check=fact_check)
    except (ValueError, json.JSONDecodeError, KeyError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await db.commit()
    return result


@router.post("/audio/transcribe")
async def transcribe_uploaded_audio(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
    user: User = Depends(authenticate),
):
    """Transcribe audio for research questions or examination-answer input."""
    try:
        transcript = await transcribe_audio(await file.read(), model)
    except (ValueError, TimeoutError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return {"transcript": transcript, "model": model or get_settings().audio_model, "intended_uses": ["research", "exam_answer_draft"]}


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
    training_example = await db.scalar(select(TrainingExample).where(
        TrainingExample.source_type == "document",
        TrainingExample.source_id == item.id,
        TrainingExample.task == "language_model",
    ))
    if training_example:
        training_example.approved = True
        training_example.approved_by = user.id
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
