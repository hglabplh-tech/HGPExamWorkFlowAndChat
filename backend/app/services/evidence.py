import hashlib
import json
import uuid
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def signature_message(
    examination_id: uuid.UUID,
    student_id: uuid.UUID,
    content_hash: str,
    signed_at: datetime,
    nonce: str,
) -> bytes:
    """Deterministic bytes signed by the student's locally held private key."""
    if signed_at.tzinfo is None:
        raise ValueError("Signing timestamp must include a timezone")
    canonical_time = signed_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    payload = {
        "content_sha256": content_hash,
        "examination_id": str(examination_id),
        "nonce": nonce,
        "signed_at": canonical_time,
        "student_id": str(student_id),
        "version": 1,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def verify_ed25519(public_key_pem: bytes, signature: bytes, message: bytes) -> None:
    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("The registered key is not an Ed25519 public key")
    try:
        key.verify(signature, message)
    except InvalidSignature as error:
        raise ValueError("Examination signature is invalid") from error
