# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for trust."""
import base64
import hashlib
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import OCSPQuery, PrivatePKI, SignatureValidation, TrustList, User, UserCertificate
from ..schemas import CertificateRevoke, PrivatePKICreate, SignatureValidationRequest, TrustListCreate, TrustListDecision, UserCertificateAssign
from ..security import authenticate, require_nonce
from ..services.audit import append_audit
from ..services.private_pki import verify_private_chain, verify_root
from ..services.ocsp import parse_ocsp_request, sign_ocsp_response
from ..services.trust import TrustValidator, parse_etsi_trust_list


from .common import (
    require_admin,
)

router = APIRouter(prefix="/api/v1")

@router.get("/trust-lists")
async def list_trust_lists(db: AsyncSession = Depends(get_db), admin: User = Depends(authenticate)):
    """Perform the list trust lists operation."""
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
    """Perform the upload trust list operation."""
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
    """Perform the decide trust list operation."""
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
    """Perform the validate signature operation."""
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
    """Perform the list private pkis operation."""
    require_admin(admin)
    items = (await db.scalars(select(PrivatePKI).order_by(PrivatePKI.name))).all()
    return [{"id": item.id, "name": item.name, "fingerprint": item.root_sha256_fingerprint, "enabled": item.enabled, "status": item.validation_status} for item in items]


@router.post("/private-pki", status_code=201)
async def create_private_pki(data: PrivatePKICreate, db: AsyncSession = Depends(get_db), admin: User = Depends(require_nonce)):
    """Perform the create private pki operation."""
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
    """Perform the decide private pki operation."""
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
    """Perform the assign user certificate operation."""
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
    """Perform the revoke user certificate operation."""
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
    """Perform the private ocsp operation."""
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
    """Perform the export private roots operation."""
    require_admin(admin)
    roots = (await db.scalars(select(PrivatePKI).where(PrivatePKI.enabled.is_(True)).order_by(PrivatePKI.name))).all()
    content = b"\n".join(item.root_certificate_pem.strip() for item in roots) + b"\n"
    return Response(content, media_type="application/x-pem-file", headers={"Content-Disposition": "attachment; filename=customer-client-roots.pem"})
