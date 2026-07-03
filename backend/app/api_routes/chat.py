# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for chat."""
import uuid
import asyncio
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Conversation, ConversationMember, Course, Enrollment, ExamGroup, Examination, Message, PrivatePKI, ResearchInteraction, Role, Submission, User
from ..schemas import ConversationCreate, ExamGroupCertificateAssign, MessageCreate, RandomExamGroupsCreate
from ..security import authenticate, hash_password, require_nonce
from ..services.audit import append_audit
from ..services.evidence import sha256_hex
from ..services.research import answer_research_question
from ..services.private_pki import verify_private_chain
from ..services.group_assignment import assign_random_groups
from ..services.audio import transcribe_audio
from ..services.ingestion import ContentExtractor, answer_from_uploaded_text


from .common import (
    active_scoring_profile, require_course_instructor, require_staff,
)

router = APIRouter(prefix="/api/v1")


@router.post("/courses/{course_id}/exam-groups/randomize", status_code=201)
async def randomize_exam_groups(
    course_id: uuid.UUID,
    data: RandomExamGroupsCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Randomly assign enrolled students to topic-specific exam chatrooms."""
    require_staff(user)
    await require_course_instructor(db, user, course_id)
    examination = await db.get(Examination, data.examination_id)
    if not examination or examination.course_id != course_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course examination not found")
    students = list(await db.scalars(select(Enrollment.user_id).where(Enrollment.course_id == course_id, Enrollment.role == Role.student)))
    if len(students) < 2:
        raise HTTPException(status.HTTP_409_CONFLICT, "At least two enrolled students are required")
    seed = data.seed or secrets.token_urlsafe(16)
    created = []
    assignments = assign_random_groups(students, data.group_size, seed)
    for index, members in enumerate(assignments):
        topic = data.topics[index % len(data.topics)]
        conversation = Conversation(
            course_id=course_id,
            title=f"{examination.title} - Group {index + 1}: {topic}",
            kind="group",
            purpose=data.purpose,
            topic=topic,
            examination_id=examination.id,
            random_assignment_seed=seed,
            created_by=user.id,
        )
        db.add(conversation)
        await db.flush()
        db.add_all(ConversationMember(conversation_id=conversation.id, user_id=member) for member in members)
        exam_group = ExamGroup(examination_id=examination.id, conversation_id=conversation.id, label=f"Group {index + 1}", topic=topic)
        db.add(exam_group)
        await db.flush()
        created.append({"group_id": exam_group.id, "conversation_id": conversation.id, "topic": topic, "member_ids": members})
    await append_audit(db, user.id, "exam_groups_randomized", "examination", examination.id, details={"group_count": len(created), "seed": seed, "purpose": data.purpose})
    await db.commit()
    return {"examination_id": examination.id, "seed": seed, "groups": created}


@router.put("/exam-groups/{group_id}/certificate")
async def assign_exam_group_certificate(
    group_id: uuid.UUID,
    data: ExamGroupCertificateAssign,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Bind an externally issued X.509 certificate to a group without its private key."""
    require_staff(user)
    group = await db.get(ExamGroup, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exam group not found")
    examination = await db.get(Examination, group.examination_id)
    await require_course_instructor(db, user, examination.course_id)
    try:
        pki = await db.get(PrivatePKI, data.private_pki_id)
        if not pki or not pki.enabled:
            raise ValueError("Enabled private PKI not found")
        details = verify_private_chain(data.certificate_pem.encode(), pki.root_certificate_pem, pki.intermediate_bundle_pem)
        now = datetime.now(UTC)
        if not details.not_valid_before <= now <= details.not_valid_after:
            raise ValueError("Certificate is outside its validity period")
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    group.certificate_pem = data.certificate_pem.encode()
    group.certificate_sha256 = details.fingerprint
    await append_audit(db, user.id, "exam_group_certificate_assigned", "exam_group", group.id, data.reason, {"certificate_sha256": details.fingerprint, "subject": details.subject})
    await db.commit()
    return {"group_id": group.id, "certificate_sha256": details.fingerprint, "subject": details.subject, "private_key_stored": False}

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
    conversation = Conversation(course_id=data.course_id, title=data.title, kind=data.kind, purpose=data.purpose, topic=data.topic, examination_id=data.examination_id, created_by=user.id)
    db.add(conversation)
    await db.flush()
    db.add_all(ConversationMember(conversation_id=conversation.id, user_id=member) for member in members)
    await append_audit(db, user.id, "conversation_created", "conversation", conversation.id, details={"members": [str(member) for member in members]})
    await db.commit()
    return {"id": conversation.id, "members": len(members)}


@router.get("/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    """List conversations visible to the current user."""
    rows = (await db.execute(
        select(Conversation).join(ConversationMember).where(ConversationMember.user_id == user.id).order_by(Conversation.title)
    )).scalars().all()
    return [{
        "id": item.id,
        "course_id": item.course_id,
        "title": item.title,
        "kind": item.kind,
        "purpose": item.purpose,
        "topic": item.topic,
        "examination_id": item.examination_id,
    } for item in rows]


async def ensure_chatbot_user(db: AsyncSession) -> User:
    """Return the internal chatbot identity used for automated room replies."""
    bot = await db.scalar(select(User).where(User.email == "chatbot@system.local"))
    if bot:
        return bot
    bot = User(
        email="chatbot@system.local",
        display_name="Chatbot",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=Role.staff,
        permissions=[],
        active=False,
    )
    db.add(bot)
    await db.flush()
    return bot


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


async def chatbot_answer_for_message(db: AsyncSession, conversation: Conversation, body: str, extra_context: str = "") -> str:
    """Answer a chatbot mention using uploaded context first and course RAG otherwise."""
    question = body.replace("@chatbot", "").strip() or "Please interpret the uploaded material."
    if extra_context.strip():
        result = answer_from_uploaded_text(question, extra_context)
        return result["answer"] or "I could not extract enough text from the uploaded file."
    course = await db.get(Course, conversation.course_id)
    profile = await active_scoring_profile(db, course) if course else None
    answer, _ = await answer_research_question(
        db, conversation.course_id, question,
        profile.semantic_profile if profile else "economy",
        profile.search_weights if profile else None,
    )
    return answer


async def attachment_from_upload(file: UploadFile) -> tuple[dict, str]:
    """Create bounded attachment metadata and optional extracted context."""
    data = await file.read()
    metadata = {"filename": file.filename or "upload", "content_type": file.content_type or "application/octet-stream", "size": len(data), "sha256": sha256_hex(data)}
    if (file.content_type or "").startswith("audio/"):
        transcript = await transcribe_audio(data)
        metadata["transcript"] = transcript
        metadata["kind"] = "audio"
        return metadata, transcript
    try:
        extracted = await asyncio.to_thread(ContentExtractor.extract, data, file.content_type or "application/octet-stream", file.filename or "")
        metadata["kind"] = "document"
        metadata["text_preview"] = extracted.text[:1000]
        return metadata, extracted.text
    except (ValueError, UnicodeError):
        metadata["kind"] = "binary"
        return metadata, ""


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
    conversation = await db.get(Conversation, conversation_id)
    item = Message(conversation_id=conversation_id, sender_id=user.id, **data.model_dump())
    db.add(item)
    chatbot_reply = None
    if "@chatbot" in data.body.casefold() and conversation:
        answer = await chatbot_answer_for_message(db, conversation, data.body)
        bot = await ensure_chatbot_user(db)
        chatbot_reply = Message(
            conversation_id=conversation_id,
            sender_id=bot.id,
            body=answer,
            shared_type="research_result",
        )
        db.add(chatbot_reply)
    await db.commit()
    return {"id": item.id, "created_at": item.created_at, "chatbot_reply_id": chatbot_reply.id if chatbot_reply else None}


@router.post("/conversations/{conversation_id}/messages/upload", status_code=201)
async def post_message_upload(
    conversation_id: uuid.UUID,
    body: str = Form(default=""),
    shared_type: str | None = Form(default=None),
    shared_id: uuid.UUID | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    """Send files or audio to a chat; chatbot uses extracted/transcribed content."""
    if not await db.get(ConversationMember, (conversation_id, user.id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Conversation membership required")
    await validate_chat_share(db, user, conversation_id, shared_type, shared_id)
    attachments, contexts = [], []
    for file in files:
        attachment, context = await attachment_from_upload(file)
        attachments.append(attachment)
        if context:
            contexts.append(context)
    conversation = await db.get(Conversation, conversation_id)
    item = Message(conversation_id=conversation_id, sender_id=user.id, body=body, attachments=attachments, shared_type=shared_type, shared_id=shared_id)
    db.add(item)
    chatbot_reply = None
    if conversation and "@chatbot" in body.casefold():
        bot = await ensure_chatbot_user(db)
        answer = await chatbot_answer_for_message(db, conversation, body, "\n\n".join(contexts))
        chatbot_reply = Message(conversation_id=conversation_id, sender_id=bot.id, body=answer, shared_type="research_result")
        db.add(chatbot_reply)
    await db.commit()
    return {"id": item.id, "attachments": attachments, "chatbot_reply_id": chatbot_reply.id if chatbot_reply else None}


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
    user_ids = {item.sender_id for item in items}
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    names = {item.id: item.display_name for item in users}
    return [{"id": item.id, "sender_id": item.sender_id, "sender_name": names.get(item.sender_id, "User"), "body": item.body, "attachments": item.attachments, "shared_type": item.shared_type, "shared_id": item.shared_id, "created_at": item.created_at} for item in reversed(items)]


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
