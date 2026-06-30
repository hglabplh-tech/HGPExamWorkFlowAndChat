# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Minimal Python client showing Basic login, bearer tokens, and request nonces."""
import base64
import json
import secrets
import uuid
from datetime import UTC, datetime

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from backend.app.services.evidence import certificate_sha256, grading_signature_message, sha256_hex, signature_message


class HcpXmlWorkflowChatClient:
    """Synchronous REST client for the HcpXmlWorkflowChat service."""
    def __init__(self, base_url: str, email: str, password: str, ca_file: str | bool = True):
        """Perform the init operation."""
        self.http = httpx.Client(base_url=base_url, verify=ca_file, timeout=20)
        response = self.http.post("/api/v1/auth/token", auth=(email, password))
        response.raise_for_status()
        self.http.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

    def _write(self, method: str, path: str, payload: dict | None = None) -> dict:
        """Perform the write operation."""
        response = self.http.request(
            method,
            path,
            headers={"X-Request-Nonce": secrets.token_urlsafe(24)},
            json=payload or {},
        )
        response.raise_for_status()
        return response.json()

    def search(self, query: str, course_id: str | None = None) -> dict:
        """Perform the search operation."""
        response = self.http.get("/api/v1/search", params={"q": query, "course_id": course_id})
        response.raise_for_status()
        return response.json()

    def ask_ai(
        self,
        course_id: str,
        question: str,
        visibility: str = "private",
        conversation_id: str | None = None,
        training_opt_in: bool = False,
    ) -> dict:
        """Perform the ask ai operation."""
        return self._write("POST", "/api/v1/research/questions", {
            "course_id": course_id,
            "question": question,
            "visibility": visibility,
            "conversation_id": conversation_id,
            "training_opt_in": training_opt_in,
        })

    def create_group(self, course_id: str, title: str, member_ids: list[str]) -> dict:
        """Perform the create group operation."""
        return self._write("POST", "/api/v1/conversations", {
            "course_id": course_id,
            "title": title,
            "member_ids": member_ids,
            "kind": "group",
        })

    def send_chat(
        self,
        conversation_id: str,
        body: str,
        shared_type: str | None = None,
        shared_id: str | None = None,
    ) -> dict:
        """Perform the send chat operation."""
        return self._write("POST", f"/api/v1/conversations/{conversation_id}/messages", {
            "body": body,
            "shared_type": shared_type,
            "shared_id": shared_id,
        })

    def chat_history(self, conversation_id: str, limit: int = 50) -> list[dict]:
        """Perform the chat history operation."""
        response = self.http.get(f"/api/v1/conversations/{conversation_id}/messages", params={"limit": limit})
        response.raise_for_status()
        return response.json()

    def release_exam(self, examination_id: str, reason: str, closes_at: str | None = None) -> dict:
        """Perform the release exam operation."""
        return self._write("POST", f"/api/v1/examinations/{examination_id}/release", {
            "reason": reason,
            "closes_at": closes_at,
        })

    def draft_exam_with_ai(
        self,
        course_id: str,
        title: str,
        learning_objectives: list[str],
        number_of_questions: int = 5,
        kind: str = "practice",
    ) -> dict:
        """Perform the draft exam with ai operation."""
        return self._write("POST", "/api/v1/examinations/draft-with-ai", {
            "course_id": course_id,
            "title": title,
            "learning_objectives": learning_objectives,
            "number_of_questions": number_of_questions,
            "kind": kind,
        })

    def request_ai_grading(self, submission_id: str) -> dict:
        """Perform the request ai grading operation."""
        return self._write("POST", f"/api/v1/submissions/{submission_id}/ai-grade")

    def return_grading(
        self,
        submission_id: str,
        exam_sha256: str,
        student_signature_sha256: str,
        teacher_grade: dict,
        private_key: Ed25519PrivateKey,
        signing_certificate_pem: str,
    ) -> dict:
        """Perform the return grading operation."""
        signed_at = datetime.now(UTC)
        grading_hash = sha256_hex(json.dumps(teacher_grade, sort_keys=True, separators=(",", ":")).encode())
        message = grading_signature_message(
            uuid.UUID(submission_id),
            exam_sha256,
            student_signature_sha256,
            grading_hash,
            signed_at,
            certificate_sha256(signing_certificate_pem.encode()),
        )
        return self._write("POST", f"/api/v1/submissions/{submission_id}/return", {
            "signature_base64": base64.b64encode(private_key.sign(message)).decode(),
            "signing_certificate_pem": signing_certificate_pem,
            "signed_at": signed_at.isoformat(),
        })

    def download_report(self, submission_id: str) -> bytes:
        """Perform the download report operation."""
        response = self.http.get(f"/api/v1/submissions/{submission_id}/report.pdf")
        response.raise_for_status()
        return response.content

    def create_course(self, code: str, title: str, discipline: str) -> dict:
        """Perform the create course operation."""
        response = self.http.post(
            "/api/v1/courses",
            headers={"X-Request-Nonce": secrets.token_urlsafe(24)},
            json={"code": code, "title": title, "discipline": discipline},
        )
        response.raise_for_status()
        return response.json()

    def register_signing_key(self, private_key: Ed25519PrivateKey) -> None:
        """Perform the register signing key operation."""
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
        signing_certificate_pem: str,
    ) -> dict:
        """Perform the submit exam operation."""
        nonce = secrets.token_urlsafe(24)
        signed_at = datetime.now(UTC)
        content = json.dumps(answers, sort_keys=True, separators=(",", ":")).encode()
        message = signature_message(
            uuid.UUID(examination_id),
            uuid.UUID(student_id),
            sha256_hex(content),
            signed_at,
            nonce,
            certificate_sha256(signing_certificate_pem.encode()),
        )
        response = self.http.post(
            "/api/v1/submissions",
            headers={"X-Request-Nonce": nonce},
            json={
                "examination_id": examination_id,
                "answers": answers,
                "content_base64": base64.b64encode(content).decode(),
                "content_type": "application/json",
                "signature_base64": base64.b64encode(private_key.sign(message)).decode(),
                "signing_certificate_pem": signing_certificate_pem,
                "signed_at": signed_at.isoformat(),
            },
        )
        response.raise_for_status()
        return response.json()


StudyClient = HcpXmlWorkflowChatClient


if __name__ == "__main__":
    client = HcpXmlWorkflowChatClient("https://localhost", "admin@example.org", "change-me", ca_file=False)
    print(client.search("photosynthesis"))
