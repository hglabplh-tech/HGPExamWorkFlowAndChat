"""Isolated RFC 6960 responder signer for customer private PKIs.

Mount /run/secrets/ocsp-config.json and referenced encrypted/private key files.
Prefer an HSM/KMS adapter instead of PEM keys in production.
"""
import base64
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509 import ocsp
from cryptography.x509.oid import OCSPExtensionOID
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Study Harbour private OCSP signer")


class SignRequest(BaseModel):
    pki_id: str
    request_der_base64: str
    certificate_status: dict


def configuration() -> dict:
    return json.loads(Path(os.environ.get("OCSP_CONFIG", "/run/secrets/ocsp-config.json")).read_text())


@app.post("/responses/sign")
async def sign_response(data: SignRequest, authorization: str = Header(default="")):
    expected = f"Bearer {os.environ.get('OCSP_SIGNER_TOKEN', '')}"
    if not expected.removeprefix("Bearer ") or authorization != expected:
        raise HTTPException(401, "Invalid service credential")
    profile = configuration().get(data.pki_id)
    if not profile:
        raise HTTPException(404, "Unknown private PKI")
    request = ocsp.load_der_ocsp_request(base64.b64decode(data.request_der_base64, validate=True))
    responder = x509.load_pem_x509_certificate(Path(profile["responder_certificate"]).read_bytes())
    password = os.environ.get(profile.get("key_password_env", "OCSP_KEY_PASSWORD"), "").encode() or None
    private_key = serialization.load_pem_private_key(Path(profile["responder_key"]).read_bytes(), password=password)
    now = datetime.now(UTC)
    state = data.certificate_status.get("status", "unknown")
    certificate_status = {
        "good": ocsp.OCSPCertStatus.GOOD,
        "revoked": ocsp.OCSPCertStatus.REVOKED,
        "unknown": ocsp.OCSPCertStatus.UNKNOWN,
    }.get(state, ocsp.OCSPCertStatus.UNKNOWN)
    revoked_at = None
    reason = None
    if certificate_status is ocsp.OCSPCertStatus.REVOKED:
        revoked_at = datetime.fromisoformat(data.certificate_status["revoked_at"])
        reason_name = data.certificate_status.get("revocation_reason", "unspecified")
        reason = getattr(x509.ReasonFlags, reason_name, x509.ReasonFlags.unspecified)
    builder = ocsp.OCSPResponseBuilder().add_response_by_hash(
        issuer_name_hash=request.issuer_name_hash,
        issuer_key_hash=request.issuer_key_hash,
        serial_number=request.serial_number,
        algorithm=request.hash_algorithm,
        cert_status=certificate_status,
        this_update=now,
        next_update=now + timedelta(minutes=10),
        revocation_time=revoked_at,
        revocation_reason=reason,
    ).responder_id(ocsp.OCSPResponderEncoding.HASH, responder).certificates([responder])
    for extension in request.extensions:
        if extension.oid == OCSPExtensionOID.NONCE:
            builder = builder.add_extension(extension.value, extension.critical)
    algorithm = None if private_key.__class__.__name__.startswith("Ed") else hashes.SHA256()
    response = builder.sign(private_key, algorithm)
    return {"response_der_base64": base64.b64encode(response.public_bytes(serialization.Encoding.DER)).decode()}
