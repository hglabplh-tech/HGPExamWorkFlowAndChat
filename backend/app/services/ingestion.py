"""Content-addressed PDF/text ingestion and PostgreSQL import/export.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import hashlib
import io
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Course, Document, TrainingExample
from .academic_integrity import fact_check_knowledge_text
from .indexing import make_chunks


SUPPORTED_TEXT_TYPES = {"text/plain", "text/markdown", "text/csv", "application/json"}


@dataclass(frozen=True)
class ExtractedContent:
    """Hold normalized text and its stable content identity."""

    text: str
    sha256: str
    media_type: str


class ContentExtractor:
    """Extract bounded UTF-8 text from supported uploads."""

    @staticmethod
    def extract(data: bytes, media_type: str, filename: str = "") -> ExtractedContent:
        """Extract and normalize PDF or text content without executing embedded data."""
        settings = get_settings()
        if len(data) > settings.upload_max_bytes:
            raise ValueError("Upload exceeds UPLOAD_MAX_BYTES")
        is_pdf = media_type == "application/pdf" or filename.casefold().endswith(".pdf")
        if is_pdf:
            reader = PdfReader(io.BytesIO(data), strict=True)
            if len(reader.pages) > settings.pdf_max_pages:
                raise ValueError("PDF exceeds PDF_MAX_PAGES")
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs are not accepted")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            media_type = "application/pdf"
        elif media_type in SUPPORTED_TEXT_TYPES or filename.casefold().endswith((".txt", ".md", ".csv", ".json")):
            text = data.decode("utf-8-sig", errors="strict")
        else:
            raise ValueError("Only PDF, UTF-8 text, Markdown, CSV, and JSON are supported")
        normalized = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
        if not normalized:
            raise ValueError("The uploaded file contains no extractable text")
        return ExtractedContent(normalized, hashlib.sha256(normalized.encode()).hexdigest(), media_type)


class KnowledgeImporter:
    """Insert genuinely new knowledge while leaving duplicates untouched."""

    @staticmethod
    async def import_document(
        db: AsyncSession,
        *,
        title: str,
        content: ExtractedContent,
        course_id: uuid.UUID | None,
        source_uri: str | None,
        metadata: dict | None = None,
        approve: bool = False,
    ) -> tuple[Document, bool]:
        """Return an existing hash match or insert a new document and training candidate."""
        existing = await db.scalar(select(Document).where(Document.content_sha256 == content.sha256))
        if existing:
            return existing, False
        document = Document(
            title=title,
            course_id=course_id,
            source_uri=source_uri,
            body_text=content.text,
            content_sha256=content.sha256,
            media_type=content.media_type,
            metadata_={**(metadata or {}), "imported_at": datetime.now(UTC).isoformat()},
            staff_approved=approve,
        )
        document.chunks = make_chunks(document)
        db.add(document)
        await db.flush()
        discipline = "General"
        if course_id and (course := await db.get(Course, course_id)):
            discipline = course.discipline
        db.add(TrainingExample(
            source_type="document",
            source_id=document.id,
            task="language_model",
            discipline=discipline,
            payload={"title": title, "text": content.text, "sha256": content.sha256},
            approved=approve,
        ))
        return document, True

    @staticmethod
    async def export_bundle(db: AsyncSession) -> dict:
        """Export courses and document metadata as a portable JSON-compatible bundle."""
        courses = (await db.scalars(select(Course))).all()
        documents = (await db.scalars(select(Document))).all()
        course_codes = {course.id: course.code for course in courses}
        return {
            "format": "hgp-exam-work-flow-and-chat/knowledge-v1",
            "exported_at": datetime.now(UTC).isoformat(),
            "courses": [{"code": x.code, "title": x.title, "discipline": x.discipline, "description": x.description} for x in courses],
            "documents": [{
                "title": x.title, "course_code": course_codes.get(x.course_id),
                "source_uri": x.source_uri, "body_text": x.body_text,
                "content_sha256": x.content_sha256, "media_type": x.media_type,
                "metadata": x.metadata_, "staff_approved": x.staff_approved,
            } for x in documents],
        }

    @classmethod
    async def import_bundle(cls, db: AsyncSession, raw: bytes, *, fact_check: bool = True) -> dict[str, int]:
        """Merge a versioned JSON bundle using course code and content hash identities."""
        bundle = json.loads(raw)
        if bundle.get("format") != "hgp-exam-work-flow-and-chat/knowledge-v1":
            raise ValueError("Unsupported knowledge bundle format")
        inserted_courses = inserted_documents = skipped = 0
        course_ids: dict[str, uuid.UUID] = {}
        for item in bundle.get("courses", []):
            course = await db.scalar(select(Course).where(Course.code == item["code"]))
            if not course:
                course = Course(**{key: item.get(key, "") for key in ("code", "title", "discipline", "description")})
                db.add(course)
                await db.flush()
                inserted_courses += 1
            course_ids[item["code"]] = course.id
        for item in bundle.get("documents", []):
            extracted = ContentExtractor.extract(item["body_text"].encode(), item.get("media_type", "text/plain"))
            fact_review = await fact_check_knowledge_text(
                extracted.text,
                rubric=item.get("metadata", {}).get("rubric", "general"),
                topic=item.get("title"),
            ) if fact_check else {"status": "disabled", "decision": "not_checked"}
            if fact_review.get("status") == "completed" and fact_review.get("decision") != "accepted" and item.get("staff_approved", False):
                skipped += 1
                continue
            course_id = course_ids.get(item.get("course_code"))
            document, created = await cls.import_document(
                db, title=item["title"], content=extracted, course_id=course_id,
                source_uri=item.get("source_uri"), metadata={**item.get("metadata", {}), "fact_check": fact_review},
                approve=bool(item.get("staff_approved", False)) and fact_review.get("decision") == "accepted",
            )
            inserted_documents += int(created)
            skipped += int(not created)
        return {"courses_inserted": inserted_courses, "documents_inserted": inserted_documents, "duplicates_skipped": skipped}


def answer_from_uploaded_text(question: str, text: str, limit: int = 3) -> dict:
    """Return the most relevant bounded passages for an upload-and-question request."""
    terms = set(re.findall(r"\w+", question.casefold()))
    passages = [part.strip() for part in re.split(r"\n{2,}|(?<=[.!?])\s+", text) if part.strip()]
    ranked = sorted(passages, key=lambda part: len(terms & set(re.findall(r"\w+", part.casefold()))), reverse=True)
    selected = ranked[:limit]
    return {"answer": " ".join(selected), "passages": selected, "mode": "extractive-upload-context"}
