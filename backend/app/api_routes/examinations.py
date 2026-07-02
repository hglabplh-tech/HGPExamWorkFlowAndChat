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
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Header, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..config import get_settings
from ..models import Conversation, ConversationMember, Course, DisciplineScoringProfile, Document, Enrollment, ExamQuestion, Examination, ExamRuleSet, GradeEvent, Message, ModelTrainingRun, OCSPQuery, PrivatePKI, ResearchInteraction, Role, SignatureValidation, Submission, TrainingExample, TrustList, User, UserCertificate, VideoResource
from ..schemas import CertificateRevoke, ConversationCreate, CourseCreate, CourseOut, DeletionRequest, DocumentCreate, ExamDraftRequest, ExaminationCreate, ExaminationJsonCreate, ExaminationRelease, ExamRuleSetCreate, GradeOverride, InstructorReturn, MessageCreate, PrivatePKICreate, PublicKeyUpdate, QuestionCreate, QuestionDraftScore, ResearchQuestionCreate, ResearchVisibilityUpdate, ScoringProfileCreate, SearchResponse, SignatureValidationRequest, SubmissionCreate, SubmissionOut, TrainingApproval, TrustListCreate, TrustListDecision, UserCertificateAssign, UserCreate, UserUpdate, VideoCreate
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
from ..services.exam_xml import export_exam_xml, import_exam_xml
from ..services.exam_json import export_exam_json, import_exam_json
from ..services.multiple_choice import score_choice_answer


from .common import (
    active_scoring_profile, build_grade_proposal, require_active_signing_certificate,
    require_admin, require_course_access, require_course_instructor, require_staff,
    require_training_manager, store_exam_report,
)

router = APIRouter(prefix="/api/v1")


async def _create_exam_from_json_payload(
    db: AsyncSession,
    user: User,
    course_id: uuid.UUID,
    payload: ExaminationJsonCreate,
) -> Examination:
    """Create a draft examination plus questions from one validated JSON payload."""
    payload.validate_exam()
    await require_course_instructor(db, user, course_id)
    if payload.rule_set_id:
        rules = await db.get(ExamRuleSet, payload.rule_set_id)
        if not rules or rules.course_id != course_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Rule set does not belong to the course")
    exam = Examination(
        course_id=course_id,
        title=payload.title,
        instructions=payload.instructions,
        kind=payload.kind,
        group_mode=payload.group_mode,
        rule_set_id=payload.rule_set_id,
        created_by=user.id,
        state="draft",
    )
    db.add(exam)
    await db.flush()
    for question in payload.questions:
        db.add(ExamQuestion(examination_id=exam.id, **question.model_dump()))
    await append_audit(db, user.id, "examination_json_imported", "examination", exam.id, details={"questions": len(payload.questions), "kind": payload.kind})
    return exam


async def _store_rule_set(data: ExamRuleSetCreate, db: AsyncSession, user: User) -> ExamRuleSet:
    """Validate and persist an immutable versioned exam rule set."""
    data.validate_rules()
    await require_course_instructor(db, user, data.course_id)
    values = data.model_dump()
    rules = {key: values.pop(key) for key in ("page_count_min", "page_count_max", "citation_style", "citation_check", "topic", "weights")}
    item = ExamRuleSet(**values, rules=rules, created_by=user.id)
    db.add(item)
    await db.flush()
    await append_audit(db, user.id, "exam_rule_set_created", "exam_rule_set", item.id, details={"name": item.name, "version": item.version})
    return item


@router.post("/exam-rule-sets", status_code=201)
async def create_exam_rule_set(data: ExamRuleSetCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Create a validated rule set from a REST JSON body."""
    require_staff(user)
    try:
        item = await _store_rule_set(data, db, user)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await db.commit()
    return {"id": item.id, "name": item.name, "version": item.version, "rules": item.rules}


@router.post("/exam-rule-sets/upload", status_code=201)
async def upload_exam_rule_file(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Upload a UTF-8 JSON rules file using the same strict schema."""
    require_staff(user)
    try:
        raw = await file.read()
        if len(raw) > 1024 * 1024:
            raise ValueError("Rules file exceeds 1 MiB")
        data = ExamRuleSetCreate.model_validate_json(raw)
        item = await _store_rule_set(data, db, user)
    except (ValueError, UnicodeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await db.commit()
    return {"id": item.id, "name": item.name, "version": item.version, "rules": item.rules}

@router.post("/examinations", status_code=201)
async def create_examination(data: ExaminationCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Perform the create examination operation."""
    require_staff(user)
    await require_course_instructor(db, user, data.course_id)
    if data.rule_set_id:
        rules = await db.get(ExamRuleSet, data.rule_set_id)
        if not rules or rules.course_id != data.course_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Rule set does not belong to the course")
    item = Examination(**data.model_dump(), created_by=user.id, state="draft")
    db.add(item)
    await db.commit()
    return {"id": item.id, "title": item.title, "kind": item.kind, "state": item.state}


@router.post("/courses/{course_id}/examinations/from-json", status_code=201)
async def create_examination_from_json(course_id: uuid.UUID, data: ExaminationJsonCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Create an instructor-reviewed exam and questions from one JSON body."""
    require_staff(user)
    try:
        exam = await _create_exam_from_json_payload(db, user, course_id, data)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await db.commit()
    return {"id": exam.id, "title": exam.title, "kind": exam.kind, "state": exam.state, "questions": len(data.questions)}


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
            "group_mode": examination.group_mode,
            "state": examination.state,
            "released_at": examination.released_at,
            "closes_at": examination.closes_at,
            "questions": [{"id": question.id, "prompt": question.prompt, "max_score": question.max_score, "question_type": question.question_type, "choices": question.choices} for question in questions],
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
    try:
        data.validate_question()
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    item = ExamQuestion(examination_id=examination_id, **data.model_dump())
    db.add(item)
    await db.commit()
    return {"id": item.id, "max_score": item.max_score}


@router.post("/examinations/{examination_id}/questions/{question_id}/score-draft")
async def score_practice_question(
    examination_id: uuid.UUID,
    question_id: uuid.UUID,
    data: QuestionDraftScore,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Score one answered practice question without submitting the whole exam."""
    examination = await db.get(Examination, examination_id)
    if not examination or examination.kind != "practice" or examination.state != "released":
        raise HTTPException(status.HTTP_409_CONFLICT, "Interactive scoring is available only for released practice examinations")
    await require_course_access(db, user, examination.course_id)
    question = await db.get(ExamQuestion, question_id)
    if not question or question.examination_id != examination.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    if question.question_type in {"single_choice", "multiple_choice"}:
        result = score_choice_answer(data.answer, question.correct_options, question.max_score, question.partial_credit)
    else:
        course = await db.get(Course, examination.course_id)
        profile = await active_scoring_profile(db, course)
        if not profile:
            raise HTTPException(status.HTTP_409_CONFLICT, "No active scoring profile exists for this discipline")
        result = await asyncio.to_thread(grade_answer, question, str(data.answer), profile)
    result["question_id"] = str(question.id)
    await append_audit(db, user.id, "practice_question_scored", "exam_question", question.id, details={"examination_id": str(examination.id), "score": result.get("score")})
    await db.commit()
    return result


@router.get("/examinations/{examination_id}/export.xml")
async def export_examination_xml(examination_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Export a course examination and optional rules as safe versioned XML."""
    examination = await db.get(Examination, examination_id)
    if not examination:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examination not found")
    await require_course_instructor(db, user, examination.course_id)
    course = await db.get(Course, examination.course_id)
    questions = (await db.scalars(select(ExamQuestion).where(ExamQuestion.examination_id == examination.id).order_by(ExamQuestion.id))).all()
    rule_set = await db.get(ExamRuleSet, examination.rule_set_id) if examination.rule_set_id else None
    payload = export_exam_xml(course.code, examination, questions, rule_set.rules if rule_set else None)
    return Response(payload, media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="exam-{examination.id}.xml"'})


@router.get("/examinations/{examination_id}/export.json")
async def export_examination_json(examination_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    """Export a course examination and answer key as versioned instructor JSON."""
    examination = await db.get(Examination, examination_id)
    if not examination:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examination not found")
    await require_course_instructor(db, user, examination.course_id)
    course = await db.get(Course, examination.course_id)
    questions = (await db.scalars(select(ExamQuestion).where(ExamQuestion.examination_id == examination.id).order_by(ExamQuestion.id))).all()
    payload = json.dumps(export_exam_json(course.code, examination, questions), indent=2).encode()
    return Response(payload, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="exam-{examination.id}.json"'})


@router.post("/courses/{course_id}/examinations/import.json", status_code=201)
async def import_examination_json(course_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Import an instructor-created JSON examination into PostgreSQL as a draft."""
    require_staff(user)
    await require_course_instructor(db, user, course_id)
    course = await db.get(Course, course_id)
    try:
        parsed = import_exam_json(await file.read())
        if parsed["course_code"] and parsed["course_code"] != course.code:
            raise ValueError("JSON course code does not match target course")
        data = ExaminationJsonCreate(**{key: parsed[key] for key in ("title", "instructions", "kind", "group_mode", "rule_set_id", "questions")})
        exam = await _create_exam_from_json_payload(db, user, course_id, data)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await db.commit()
    return {"id": exam.id, "state": "draft", "questions": len(data.questions)}


@router.post("/courses/{course_id}/examinations/import.xml", status_code=201)
async def import_examination_xml(course_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    """Import a reviewed XML examination into PostgreSQL as a draft."""
    require_staff(user)
    await require_course_instructor(db, user, course_id)
    course = await db.get(Course, course_id)
    try:
        parsed = import_exam_xml(await file.read())
        if parsed["course_code"] and parsed["course_code"] != course.code:
            raise ValueError("XML course code does not match target course")
        exam = Examination(course_id=course_id, title=parsed["title"], instructions=parsed["instructions"], kind=parsed["kind"], group_mode=parsed["group_mode"], state="draft", created_by=user.id)
        db.add(exam)
        await db.flush()
        for values in parsed["questions"]:
            question = QuestionCreate(**values)
            question.validate_question()
            db.add(ExamQuestion(examination_id=exam.id, **question.model_dump()))
    except (ValueError, TypeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await append_audit(db, user.id, "examination_xml_imported", "examination", exam.id, details={"course_code": course.code})
    await db.commit()
    return {"id": exam.id, "state": "draft", "questions": len(parsed["questions"])}
