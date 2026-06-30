import base64

import httpx
from cryptography.x509 import ocsp

from ..config import get_settings


def parse_ocsp_request(request_der: bytes) -> dict:
    try:
        request = ocsp.load_der_ocsp_request(request_der)
    except ValueError as error:
        raise ValueError("Malformed DER OCSP request") from error
    return {
        "serial_number": format(request.serial_number, "x"),
        "issuer_name_hash": request.issuer_name_hash.hex(),
        "issuer_key_hash": request.issuer_key_hash.hex(),
        "hash_algorithm": request.hash_algorithm.name,
    }


async def sign_ocsp_response(request_der: bytes, status: dict, pki_id: str) -> bytes:
    settings = get_settings()
    if not settings.ocsp_signer_url:
        raise RuntimeError("OCSP_SIGNER_URL is not configured")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{settings.ocsp_signer_url.rstrip('/')}/responses/sign",
            json={
                "pki_id": pki_id,
                "request_der_base64": base64.b64encode(request_der).decode(),
                "certificate_status": status,
            },
            headers={"Authorization": f"Bearer {settings.ocsp_signer_token.get_secret_value()}"},
        )
        response.raise_for_status()
        return base64.b64decode(response.json()["response_der_base64"], validate=True)
