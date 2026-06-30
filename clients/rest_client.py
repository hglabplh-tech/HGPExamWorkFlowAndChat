"""Minimal Python client showing Basic login, bearer tokens, and request nonces."""
import base64
import json
import secrets
import uuid
from datetime import UTC, datetime

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from backend.app.services.evidence import sha256_hex, signature_message


class StudyClient:
    def __init__(self, base_url: str, email: str, password: str, ca_file: str | bool = True):
        self.http = httpx.Client(base_url=base_url, verify=ca_file, timeout=20)
        response = self.http.post("/api/v1/auth/token", auth=(email, password))
        response.raise_for_status()
        self.http.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

    def search(self, query: str, course_id: str | None = None) -> dict:
        response = self.http.get("/api/v1/search", params={"q": query, "course_id": course_id})
        response.raise_for_status()
        return response.json()

    def create_course(self, code: str, title: str, discipline: str) -> dict:
        response = self.http.post(
            "/api/v1/courses",
            headers={"X-Request-Nonce": secrets.token_urlsafe(24)},
            json={"code": code, "title": title, "discipline": discipline},
        )
        response.raise_for_status()
        return response.json()

    def register_signing_key(self, private_key: Ed25519PrivateKey) -> None:
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        response = self.http.put(
            "/api/v1/users/me/signing-key",
            headers={"X-Request-Nonce": secrets.token_urlsafe(24)},
            json={"public_key_pem": public_pem},
        )
        response.raise_for_status()

    def submit_exam(
        self,
        examination_id: str,
        student_id: str,
        answers: dict[str, str],
        private_key: Ed25519PrivateKey,
    ) -> dict:
        nonce = secrets.token_urlsafe(24)
        signed_at = datetime.now(UTC)
        content = json.dumps(answers, sort_keys=True, separators=(",", ":")).encode()
        message = signature_message(uuid.UUID(examination_id), uuid.UUID(student_id), sha256_hex(content), signed_at, nonce)
        response = self.http.post(
            "/api/v1/submissions",
            headers={"X-Request-Nonce": nonce},
            json={
                "examination_id": examination_id,
                "answers": answers,
                "content_base64": base64.b64encode(content).decode(),
                "content_type": "application/json",
                "signature_base64": base64.b64encode(private_key.sign(message)).decode(),
                "signed_at": signed_at.isoformat(),
            },
        )
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    client = StudyClient("https://localhost", "admin@example.org", "change-me", ca_file=False)
    print(client.search("photosynthesis"))
