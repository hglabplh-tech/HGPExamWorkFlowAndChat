# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Vocabulary-file generation for search and local model training."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Document
from .bm25 import tokenize


async def build_vocabulary_bundle(db: AsyncSession, *, min_frequency: int = 1, limit: int = 50000) -> dict:
    """Build a JSON vocabulary bundle from approved PostgreSQL knowledge documents."""
    rows = (await db.scalars(select(Document).where(Document.staff_approved.is_(True)))).all()
    counts: Counter[str] = Counter()
    for document in rows:
        counts.update(tokenize(document.body_text))
    terms = [
        {"token": token, "frequency": frequency}
        for token, frequency in counts.most_common(limit)
        if frequency >= min_frequency
    ]
    return {
        "format": "hcp-xml-workflow-chat/vocabulary-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "min_frequency": min_frequency,
        "document_count": len(rows),
        "terms": terms,
    }


def vocabulary_text(bundle: dict) -> str:
    """Render a JSON vocabulary bundle as a one-token-per-line vocab file."""
    return "\n".join(item["token"] for item in bundle.get("terms", [])) + "\n"
