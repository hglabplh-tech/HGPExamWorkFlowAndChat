# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for search."""
import uuid
import asyncio

import chromadb

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import SearchHit, SearchResponse
from ..config import get_settings
from .embeddings import encode
from .search_ranking import HybridRanker


def _semantic_search(query: str, course_id: uuid.UUID | None, limit: int, profile: str) -> list[SearchHit]:
    """Perform the semantic search operation."""
    settings = get_settings()
    host = settings.chroma_url.removeprefix("http://").removeprefix("https://")
    hostname, _, port = host.partition(":")
    client = chromadb.HttpClient(host=hostname, port=int(port or 8000), ssl=settings.chroma_url.startswith("https"))
    collection = client.get_collection(f"approved_knowledge_{profile}")
    where = {"$or": [{"course_id": "global"}, {"course_id": str(course_id)}]} if course_id else None
    arguments = {"query_embeddings": encode(profile, [query], settings.compute_device), "n_results": limit}
    if where:
        arguments["where"] = where
    result = collection.query(**arguments)
    hits: list[SearchHit] = []
    for metadata, document, distance in zip(result["metadatas"][0], result["documents"][0], result["distances"][0]):
        hits.append(SearchHit(
            kind="document",
            id=uuid.UUID(metadata["document_id"]),
            title=metadata["title"],
            excerpt=document[:500],
            score=1.0 / (1.0 + float(distance)),
        ))
    return hits


async def hybrid_search(
    db: AsyncSession,
    query: str,
    course_id: uuid.UUID | None,
    limit: int = 10,
    profile: str = "economy",
    weights: dict[str, float] | None = None,
) -> SearchResponse:
    """Perform the hybrid search operation."""
    weights = weights or {"full_text": 0.4, "semantic": 0.6}
    rows = (
        await db.execute(
            text("""
                SELECT d.id, d.title,
                       ts_headline('simple', c.text, websearch_to_tsquery('simple', :query),
                                   'MaxWords=35, MinWords=12') AS excerpt,
                       ts_rank_cd(to_tsvector('simple', c.text), websearch_to_tsquery('simple', :query)) AS score
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.staff_approved = true
                  AND (CAST(:course_id AS uuid) IS NULL OR d.course_id IS NULL OR d.course_id = CAST(:course_id AS uuid))
                  AND to_tsvector('simple', c.text) @@ websearch_to_tsquery('simple', :query)
                ORDER BY score DESC LIMIT :limit
            """),
            {"query": query, "course_id": str(course_id) if course_id else None, "limit": limit},
        )
    ).mappings().all()
    hits = [SearchHit(kind="document", **row) for row in rows]

    video_rows = (
        await db.execute(
            text("""
                SELECT id, title, left(description, 240) AS excerpt,
                       similarity(title || ' ' || description, :query) AS score,
                       youtube_url AS url
                FROM video_resources
                WHERE staff_approved = true
                  AND (CAST(:course_id AS uuid) IS NULL OR course_id IS NULL OR course_id = CAST(:course_id AS uuid))
                  AND similarity(title || ' ' || description, :query) > 0.05
                ORDER BY score DESC LIMIT :limit
            """),
            {"query": query, "course_id": str(course_id) if course_id else None, "limit": limit},
        )
    ).mappings().all()
    hits.extend(SearchHit(kind="video", **row) for row in video_rows)
    try:
        semantic = await asyncio.to_thread(_semantic_search, query, course_id, limit, profile)
    except Exception:
        semantic = []  # lexical search remains available while the derived index rebuilds

    hits = HybridRanker.fuse({"full_text": hits, "semantic": semantic}, weights)
    warning = None if hits else "No approved sources cover this query yet; staff review is recommended."
    return SearchResponse(query=query, results=hits[:limit], coverage_warning=warning)
