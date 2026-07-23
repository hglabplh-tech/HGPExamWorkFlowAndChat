# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Certificate-bound envelope encryption for sensitive exam and grading data."""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .evidence import certificate_sha256, sha256_hex


def _b64(data: bytes) -> str:
    """Encode binary payloads for JSONB storage."""
    return base64.b64encode(data).decode("ascii")


def _json_bytes(value: Any) -> bytes:
    """Serialize sensitive values canonically before encryption."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def encrypt_bytes_for_certificate(plaintext: bytes, certificate_pem: bytes, purpose: str) -> dict[str, Any]:
    """Encrypt bytes for an RSA-capable X.509 recipient certificate."""
    certificate = x509.load_pem_x509_certificate(certificate_pem)
    public_key = certificate.public_key()
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError("Recipient certificate is not usable for RSA-OAEP encryption")
    cek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    aad = purpose.encode("utf-8")
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext, aad)
    wrapped_key = public_key.encrypt(
        cek,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=purpose.encode("utf-8")),
    )
    return {
        "version": 1,
        "algorithm": "AES-256-GCM",
        "key_wrap": "RSA-OAEP-SHA256",
        "purpose": purpose,
        "certificate_sha256": certificate_sha256(certificate_pem),
        "plaintext_sha256": sha256_hex(plaintext),
        "aad": purpose,
        "nonce": _b64(nonce),
        "wrapped_key": _b64(wrapped_key),
        "ciphertext": _b64(ciphertext),
    }


def encrypt_json_for_certificate(value: Any, certificate_pem: bytes, purpose: str) -> dict[str, Any]:
    """Encrypt JSON-compatible data for one certificate recipient."""
    return encrypt_bytes_for_certificate(_json_bytes(value), certificate_pem, purpose)


def best_effort_encrypt_json(value: Any, certificate_pem: bytes | None, purpose: str) -> tuple[dict[str, Any] | None, str]:
    """Encrypt when possible and return a machine-readable status."""
    if not certificate_pem:
        return None, "missing_certificate"
    try:
        return encrypt_json_for_certificate(value, certificate_pem, purpose), "encrypted"
    except ValueError as error:
        return {"status": "not_encrypted", "reason": str(error), "purpose": purpose}, "unsupported_certificate"


def best_effort_encrypt_bytes(value: bytes, certificate_pem: bytes | None, purpose: str) -> tuple[dict[str, Any] | None, str]:
    """Encrypt bytes when possible and return a machine-readable status."""
    if not certificate_pem:
        return None, "missing_certificate"
    try:
        return encrypt_bytes_for_certificate(value, certificate_pem, purpose), "encrypted"
    except ValueError as error:
        return {"status": "not_encrypted", "reason": str(error), "purpose": purpose}, "unsupported_certificate"
