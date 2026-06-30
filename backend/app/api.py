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
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .database import get_db
from .config import get_settings
from .models import Conversation, ConversationMember, Course, DisciplineScoringProfile, Document, Enrollment, ExamQuestion, Examination, GradeEvent, Message, OCSPQuery, PrivatePKI, Role, SignatureValidation, Submission, TrustList, User, UserCertificate, VideoResource
from .schemas import CertificateRevoke, ConversationCreate, CourseCreate, CourseOut, DeletionRequest, DocumentCreate, ExaminationCreate, GradeOverride, PrivatePKICreate, PublicKeyUpdate, QuestionCreate, ScoringProfileCreate, SearchResponse, SignatureValidationRequest, SubmissionCreate, SubmissionOut, TrustListCreate, TrustListDecision, UserCertificateAssign, UserCreate, UserUpdate, VideoCreate
from .security import authenticate, create_access_token, hash_password, require_nonce
from .services.audit import append_audit
from .services.asag import grade_answer
from .services.evidence import sha256_hex, signature_message, verify_ed25519
from .services.indexing import index_approved_document, make_chunks
from .services.model_router import select_models
from .services.private_pki import verify_private_chain, verify_root
from .services.ocsp import parse_ocsp_request, sign_ocsp_response
from .services.search import hybrid_search
from .services.trust import TrustValidator, parse_etsi_trust_list

router = APIRouter(prefix="/api/v1")


def require_staff(user: User) -> None:
    if user.role not in {Role.teacher, Role.staff, Role.admin}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff permission required")


def require_admin(user: User) -> None:
    if user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator permission required")


@router.post("/auth/token")
async def token(user: User = Depends(authenticate)) -> dict:
    return {"access_token": create_access_token(user), "token_type": "bearer"}


@router.put("/users/me/signing-key")
async def register_signing_key(data: PublicKeyUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    try:
        verify_ed25519(data.public_key_pem.encode(), b"\0" * 64, b"validation")
    except ValueError as error:
        if "signature is invalid" not in str(error):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    user.signing_public_key = data.public_key_pem.encode()
    await append_audit(db, user.id, "signing_key_registered", "user", user.id)
    await db.commit()
    return {"status": "registered", "algorithm": "Ed25519"}


@router.post("/users", status_code=201)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    require_admin(admin)
    try:
        role = Role(data.role)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown role") from error
    user = User(email=data.email, display_name=data.display_name, password_hash=hash_password(data.password), role=role)
    db.add(user)
    await db.flush()
    await append_audit(db, admin.id, "user_created", "user", user.id, details={"role": role.value})
    await db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), admin: User = Depends(authenticate)):
    require_admin(admin)
    users = (await db.scalars(select(User).order_by(User.email))).all()
    return [{"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role, "active": user.active} for user in users]


@router.patch("/users/{user_id}")
async def update_user(user_id: uuid.UUID, data: UserUpdate, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    require_admin(admin)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    values = data.model_dump(exclude_none=True)
    if "role" in values:
        try:
            values["role"] = Role(values["role"])
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown role") from error
    for key, value in values.items():
        setattr(user, key, value)
    audit_values = {key: value.value if isinstance(value, Role) else value for key, value in values.items()}
    await append_audit(db, admin.id, "user_updated", "user", user.id, details=audit_values)
    await db.commit()
    return {"id": user.id, "status": "updated"}


@router.delete("/users/{user_id}")
async def deactivate_user(user_id: uuid.UUID, data: DeletionRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    require_admin(admin)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.active = False
    user.deleted_at = datetime.now(UTC)
    await append_audit(db, admin.id, "user_deactivated", "user", user.id, data.reason)
    await db.commit()
    return {"id": user.id, "status": "deactivated"}


@router.get("/trust-lists")
async def list_trust_lists(db: AsyncSession = Depends(get_db), admin: User = Depends(authenticate)):
    require_admin(admin)
    items = (await db.scalars(select(TrustList).order_by(TrustList.created_at.desc()))).all()
    return [{
        "id": item.id,
        "name": item.name,
        "framework": item.framework,
        "territory": item.territory,
        "tsl_version": item.tsl_version,
        "sha256": item.sha256,
        "official": item.is_official,
        "enabled": item.enabled,
        "signature_status": item.signature_status,
    } for item in items]


@router.post("/trust-lists", status_code=201)
async def upload_trust_list(data: TrustListCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    require_admin(admin)
    if data.is_official:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Official status can only be assigned by the verified EU LOTL synchronization process")
    try:
        parsed = parse_etsi_trust_list(base64.b64decode(data.xml_base64, validate=True))
    except (ValueError, TypeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    status_value, report = "validator_unavailable", {}
    try:
        report = await TrustValidator().validate_trust_list(parsed.content, data.framework)
        status_value = report.get("status", "indeterminate")
    except (RuntimeError, httpx.HTTPError) as error:
        report = {"error": str(error)}
    item = TrustList(
        name=data.name,
        framework=data.framework,
        territory=data.territory or parsed.scheme_territory,
        source_url=data.source_url,
        xml_content=parsed.content,
        sha256=parsed.sha256,
        tsl_version=parsed.version,
        is_official=False,
        enabled=False,
        signature_status=status_value,
        validation_report=report,
        uploaded_by=admin.id,
    )
    db.add(item)
    await db.flush()
    await append_audit(db, admin.id, "trust_list_uploaded", "trust_list", item.id, details={"sha256": item.sha256, "status": status_value})
    await db.commit()
    return {"id": item.id, "signature_status": status_value, "enabled": False}


@router.post("/trust-lists/{trust_list_id}/decision")
async def decide_trust_list(trust_list_id: uuid.UUID, data: TrustListDecision, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    require_admin(admin)
    item = await db.get(TrustList, trust_list_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trusted list not found")
    if data.enable and item.signature_status not in {"valid", "valid_private"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "A trusted list must have a valid cryptographic signature before activation")
    item.enabled = data.enable
    await append_audit(db, admin.id, "trust_list_enabled" if data.enable else "trust_list_disabled", "trust_list", item.id, data.reason, {"framework": item.framework})
    await db.commit()
    return {"id": item.id, "enabled": item.enabled}


@router.post("/signatures/validate", status_code=201)
async def validate_signature(data: SignatureValidationRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    try:
        document = base64.b64decode(data.signed_document_base64, validate=True)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signed document is not valid base64") from error
    if len(document) > 100 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Signed document exceeds 100 MiB")
    trust_lists: list[TrustList] = []
    for trust_list_id in data.trust_list_ids:
        item = await db.get(TrustList, trust_list_id)
        if not item or not item.enabled or item.signature_status not in {"valid", "valid_private"}:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Trusted list {trust_list_id} is unavailable or unverified")
        trust_lists.append(item)
    try:
        report = await TrustValidator().validate_signature(
            document,
            data.signature_format,
            data.framework,
            [item.xml_content for item in trust_lists],
            data.validation_time.isoformat() if data.validation_time else None,
        )
    except RuntimeError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Signature validation service failed") from error
    record = SignatureValidation(
        document_sha256=hashlib.sha256(document).hexdigest(),
        framework=data.framework,
        signature_format=data.signature_format,
        status=report.get("status", "indeterminate"),
        qualification=report.get("qualification"),
        signer_subject=report.get("signer_subject"),
        trusted_list_ids=[str(item.id) for item in trust_lists],
        report=report,
        validated_by=user.id,
    )
    db.add(record)
    await db.flush()
    await append_audit(db, user.id, "signature_validated", "signature_validation", record.id, details={"status": record.status, "framework": record.framework, "sha256": record.document_sha256})
    await db.commit()
    return {"id": record.id, "status": record.status, "qualification": record.qualification, "report": report}


@router.get("/private-pki")
async def list_private_pkis(db: AsyncSession = Depends(get_db), admin: User = Depends(authenticate)):
    require_admin(admin)
    items = (await db.scalars(select(PrivatePKI).order_by(PrivatePKI.name))).all()
    return [{"id": item.id, "name": item.name, "fingerprint": item.root_sha256_fingerprint, "enabled": item.enabled, "status": item.validation_status} for item in items]


@router.post("/private-pki", status_code=201)
async def create_private_pki(data: PrivatePKICreate, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    require_admin(admin)
    root_pem = data.root_certificate_pem.encode()
    intermediates = data.intermediate_bundle_pem.encode()
    try:
        root = verify_root(root_pem)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    item = PrivatePKI(
        name=data.name,
        root_certificate_pem=root_pem,
        intermediate_bundle_pem=intermediates,
        root_sha256_fingerprint=root.fingerprint,
        enabled=False,
        validation_status="valid_private_root",
        ocsp_responder_url=data.ocsp_responder_url,
        ocsp_responder_certificate_pem=data.ocsp_responder_certificate_pem.encode() if data.ocsp_responder_certificate_pem else None,
        created_by=admin.id,
    )
    db.add(item)
    await db.flush()
    await append_audit(db, admin.id, "private_pki_created", "private_pki", item.id, details={"root_fingerprint": root.fingerprint})
    await db.commit()
    return {"id": item.id, "root_fingerprint": root.fingerprint, "enabled": False}


@router.post("/private-pki/{pki_id}/decision")
async def decide_private_pki(pki_id: uuid.UUID, data: TrustListDecision, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    require_admin(admin)
    item = await db.get(PrivatePKI, pki_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Private PKI not found")
    if data.enable and item.validation_status != "valid_private_root":
        raise HTTPException(status.HTTP_409_CONFLICT, "Private root has not been validated")
    item.enabled = data.enable
    await append_audit(db, admin.id, "private_pki_enabled" if data.enable else "private_pki_disabled", "private_pki", item.id, data.reason)
    await db.commit()
    return {"id": item.id, "enabled": item.enabled}


@router.put("/private-pki/{pki_id}/users/{user_id}/certificate")
async def assign_user_certificate(
    pki_id: uuid.UUID,
    user_id: uuid.UUID,
    data: UserCertificateAssign,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_nonce),
):
    require_admin(admin)
    pki, user = await db.get(PrivatePKI, pki_id), await db.get(User, user_id)
    if not pki or not pki.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Private PKI is missing or disabled")
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    certificate_pem = data.certificate_pem.encode()
    try:
        details = verify_private_chain(certificate_pem, pki.root_certificate_pem, pki.intermediate_bundle_pem)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    certificate = UserCertificate(
        user_id=user.id,
        private_pki_id=pki.id,
        certificate_pem=certificate_pem,
        sha256_fingerprint=details.fingerprint,
        subject=details.subject,
        serial_number=details.serial_number,
        not_valid_before=details.not_valid_before,
        not_valid_after=details.not_valid_after,
        assigned_by=admin.id,
    )
    db.add(certificate)
    user.client_cert_fingerprint = details.fingerprint
    await db.flush()
    await append_audit(db, admin.id, "user_certificate_assigned", "user_certificate", certificate.id, data.reason, {"user_id": str(user.id), "fingerprint": details.fingerprint})
    await db.commit()
    return {"id": certificate.id, "user_id": user.id, "fingerprint": details.fingerprint, "subject": details.subject}


@router.post("/user-certificates/{certificate_id}/revoke")
async def revoke_user_certificate(certificate_id: uuid.UUID, data: CertificateRevoke, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    require_admin(admin)
    certificate = await db.get(UserCertificate, certificate_id)
    if not certificate:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User certificate not found")
    certificate.revoked = True
    certificate.revoked_at = datetime.now(UTC)
    certificate.revocation_reason = data.reason
    user = await db.get(User, certificate.user_id)
    if user and user.client_cert_fingerprint == certificate.sha256_fingerprint:
        user.client_cert_fingerprint = None
    await append_audit(db, admin.id, "user_certificate_revoked", "user_certificate", certificate.id, data.comment, {"reason": data.reason})
    await db.commit()
    return {"id": certificate.id, "status": "revoked", "revoked_at": certificate.revoked_at}


@router.post("/ocsp/{pki_id}")
async def private_ocsp(pki_id: uuid.UUID, request_der: bytes = Body(media_type="application/ocsp-request"), db: AsyncSession = Depends(get_db)):
    pki = await db.get(PrivatePKI, pki_id)
    if not pki or not pki.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "OCSP responder not found")
    try:
        request = parse_ocsp_request(request_der)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    certificate = await db.scalar(select(UserCertificate).where(
        UserCertificate.private_pki_id == pki.id,
        UserCertificate.serial_number == request["serial_number"],
    ))
    certificate_status = {
        "status": "unknown" if not certificate else "revoked" if certificate.revoked else "good",
        "revoked_at": certificate.revoked_at.isoformat() if certificate and certificate.revoked_at else None,
        "revocation_reason": certificate.revocation_reason if certificate else None,
    }
    try:
        response_der = await sign_ocsp_response(request_der, certificate_status, str(pki.id))
    except RuntimeError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    except (httpx.HTTPError, ValueError, KeyError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "OCSP signing service failed") from error
    db.add(OCSPQuery(
        private_pki_id=pki.id,
        serial_number=request["serial_number"],
        request_sha256=hashlib.sha256(request_der).hexdigest(),
        response_sha256=hashlib.sha256(response_der).hexdigest(),
        certificate_status=certificate_status["status"],
    ))
    await db.commit()
    return Response(response_der, media_type="application/ocsp-response", headers={"Cache-Control": "no-store"})


@router.get("/private-pki-roots.pem")
async def export_private_roots(db: AsyncSession = Depends(get_db), admin: User = Depends(authenticate)):
    require_admin(admin)
    roots = (await db.scalars(select(PrivatePKI).where(PrivatePKI.enabled.is_(True)).order_by(PrivatePKI.name))).all()
    content = b"\n".join(item.root_certificate_pem.strip() for item in roots) + b"\n"
    return Response(content, media_type="application/x-pem-file", headers={"Content-Disposition": "attachment; filename=customer-client-roots.pem"})


@router.get("/courses", response_model=list[CourseOut])
async def courses(db: AsyncSession = Depends(get_db), _: User = Depends(authenticate)):
    return (await db.scalars(select(Course).order_by(Course.code))).all()


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(data: CourseCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    require_staff(user)
    item = Course(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/scoring-profiles", status_code=201)
async def create_scoring_profile(data: ScoringProfileCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    require_staff(user)
    try:
        data.validate_weights()
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    version = (await db.scalar(select(func.max(DisciplineScoringProfile.version)).where(
        DisciplineScoringProfile.discipline == data.discipline,
    ))) or 0
    await db.execute(update(DisciplineScoringProfile).where(
        DisciplineScoringProfile.discipline == data.discipline,
        DisciplineScoringProfile.active.is_(True),
    ).values(active=False))
    profile = DisciplineScoringProfile(
        discipline=data.discipline,
        version=version + 1,
        grading_weights=data.grading_weights,
        search_weights=data.search_weights,
        semantic_profile=data.semantic_profile,
        created_by=user.id,
    )
    db.add(profile)
    await db.flush()
    await append_audit(db, user.id, "scoring_profile_created", "discipline_scoring_profile", profile.id, details={"discipline": profile.discipline, "version": profile.version, "grading_weights": profile.grading_weights, "search_weights": profile.search_weights})
    await db.commit()
    return {"id": profile.id, "discipline": profile.discipline, "version": profile.version}


@router.get("/scoring-profiles")
async def scoring_profiles(discipline: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    require_staff(user)
    query = select(DisciplineScoringProfile).order_by(DisciplineScoringProfile.discipline, DisciplineScoringProfile.version.desc())
    if discipline:
        query = query.where(DisciplineScoringProfile.discipline == discipline)
    items = (await db.scalars(query)).all()
    return [{"id": item.id, "discipline": item.discipline, "version": item.version, "active": item.active, "grading_weights": item.grading_weights, "search_weights": item.search_weights, "semantic_profile": item.semantic_profile} for item in items]


@router.post("/examinations", status_code=201)
async def create_examination(data: ExaminationCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    require_staff(user)
    item = Examination(**data.model_dump())
    db.add(item)
    await db.commit()
    return {"id": item.id, "title": item.title}


@router.post("/examinations/{examination_id}/questions", status_code=201)
async def create_question(examination_id: uuid.UUID, data: QuestionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    require_staff(user)
    if not await db.get(Examination, examination_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examination not found")
    item = ExamQuestion(examination_id=examination_id, **data.model_dump())
    db.add(item)
    await db.commit()
    return {"id": item.id, "max_score": item.max_score}


@router.post("/documents", status_code=201)
async def create_document(data: DocumentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
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
    require_staff(user)
    item = VideoResource(**data.model_dump(mode="json"))
    db.add(item)
    await db.commit()
    return {"id": item.id, "status": "awaiting_staff_approval"}


@router.post("/videos/{video_id}/approve")
async def approve_video(video_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
    require_staff(user)
    item = await db.get(VideoResource, video_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    item.staff_approved = True
    await db.commit()
    return {"id": item.id, "status": "approved"}


@router.get("/videos.csv")
async def export_videos(db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
    require_staff(user)
    output = io.StringIO()
    fields = ["youtube_url", "youtube_video_id", "title", "description", "discipline", "course_id", "question_tags", "keywords", "staff_approved"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for video in (await db.scalars(select(VideoResource))).all():
        writer.writerow({name: getattr(video, name) for name in fields})
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=videos.csv"})


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=2, max_length=500),
    course_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
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
    return select_models(q, profile, device).__dict__


@router.get("/coverage")
async def coverage(db: AsyncSession = Depends(get_db), user: User = Depends(authenticate)):
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


@router.post("/submissions", response_model=SubmissionOut, status_code=201)
async def submit(
    data: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
    nonce: str = Header(alias="X-Request-Nonce"),
):
    if not user.signing_public_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "Register a signing public key before submitting")
    try:
        content = data.content_bytes()
        signature = data.signature_bytes()
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid base64 evidence") from error
    content_hash = sha256_hex(content)
    if data.content_type == "application/json":
        try:
            if json.loads(content) != data.answers:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signed JSON content does not match answers")
        except json.JSONDecodeError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signed examination content is not valid JSON") from error
    now = datetime.now(UTC)
    if data.signed_at.tzinfo is None or abs((now - data.signed_at.astimezone(UTC)).total_seconds()) > get_settings().signature_clock_skew_seconds:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signing timestamp is outside the permitted clock window")
    message = signature_message(data.examination_id, user.id, content_hash, data.signed_at, nonce)
    try:
        verify_ed25519(user.signing_public_key, signature, message)
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
        client_signed_at=data.signed_at,
        receipt_nonce=nonce,
        retention_until=retention_until,
        submitted_at=now,
    )
    db.add(item)
    await db.flush()
    await append_audit(db, user.id, "examination_submitted", "submission", item.id, details={"sha256": content_hash, "retention_until": retention_until.isoformat()})
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/submissions/{submission_id}")
async def delete_submission(submission_id: uuid.UUID, data: DeletionRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
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
    require_admin(admin)
    item = await db.get(Submission, submission_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    item.legal_hold = False
    await append_audit(db, admin.id, "legal_hold_released", "submission", item.id, data.reason)
    await db.commit()
    return {"id": item.id, "legal_hold": False}


@router.post("/conversations", status_code=201)
async def create_conversation(data: ConversationCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_nonce)):
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


@router.get("/conversations/{conversation_id}/shared-submissions/{submission_id}")
async def shared_submission(
    conversation_id: uuid.UUID,
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(authenticate),
):
    member = await db.get(ConversationMember, (conversation_id, user.id))
    if not member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Conversation membership required")
    share = await db.scalar(select(Message).where(
        Message.conversation_id == conversation_id,
        Message.shared_type == "submission",
        Message.shared_id == submission_id,
    ))
    if not share:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission was not shared in this conversation")
    item = await db.get(Submission, submission_id)
    if not item or item.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    return {"id": item.id, "answers": item.answers, "ai_grade": item.ai_grade, "teacher_grade": item.teacher_grade}


@router.post("/submissions/{submission_id}/ai-grade")
async def propose_ai_grade(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    require_staff(user)
    submission = await db.get(Submission, submission_id)
    if not submission or submission.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    examination = await db.get(Examination, submission.examination_id)
    course = await db.get(Course, examination.course_id) if examination else None
    if not course:
        raise HTTPException(status.HTTP_409_CONFLICT, "Submission has no valid course")
    profile = await db.scalar(select(DisciplineScoringProfile).where(
        DisciplineScoringProfile.discipline == course.discipline,
        DisciplineScoringProfile.active.is_(True),
    ).order_by(DisciplineScoringProfile.version.desc()))
    if not profile:
        raise HTTPException(status.HTTP_409_CONFLICT, "No active scoring profile exists for this discipline")
    questions = (await db.scalars(select(ExamQuestion).where(
        ExamQuestion.examination_id == examination.id,
    ).order_by(ExamQuestion.id))).all()
    results = []
    for question in questions:
        answer = str(submission.answers.get(str(question.id), ""))
        results.append(await asyncio.to_thread(grade_answer, question, answer, profile))
        results[-1]["question_id"] = str(question.id)
    proposal = {
        "profile_id": str(profile.id),
        "profile_version": profile.version,
        "discipline": profile.discipline,
        "questions": results,
        "total": round(sum(result["score"] for result in results), 3),
        "maximum": round(sum(result["max_score"] for result in results), 3),
        "requires_teacher_review": any(result["requires_teacher_review"] for result in results),
        "status": "provisional",
    }
    submission.ai_grade = proposal
    db.add(GradeEvent(submission_id=submission.id, actor_id=user.id, kind="ai_proposal", grade=proposal, reason="Weighted ASAG scoring"))
    await append_audit(db, user.id, "ai_grade_proposed", "submission", submission.id, details={"profile_id": str(profile.id), "total": proposal["total"], "requires_teacher_review": proposal["requires_teacher_review"]})
    await db.commit()
    return proposal


@router.post("/submissions/{submission_id}/teacher-override")
async def override_grade(
    submission_id: uuid.UUID,
    data: GradeOverride,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_nonce),
):
    require_staff(user)
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    grade = data.model_dump(exclude={"reason"})
    submission.teacher_grade = grade
    db.add(GradeEvent(submission_id=submission.id, actor_id=user.id, kind="teacher_override", grade=grade, reason=data.reason))
    await append_audit(db, user.id, "teacher_grade_override", "submission", submission.id, data.reason, {"grade": grade})
    await db.commit()
    return {"submission_id": submission.id, "effective_grade": grade, "overridden_by": user.id}
