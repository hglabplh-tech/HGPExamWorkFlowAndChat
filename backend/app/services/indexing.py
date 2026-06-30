# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for indexing."""
import uuid

import chromadb

from ..config import get_settings
from ..models import Document, DocumentChunk
from .embeddings import encode


def split_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    """Perform the split text operation."""
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - overlap
    return chunks


def make_chunks(document: Document) -> list[DocumentChunk]:
    """Perform the make chunks operation."""
    return [
        DocumentChunk(ordinal=i, text=text, search_text=text, chroma_id=str(uuid.uuid4()))
        for i, text in enumerate(split_text(document.body_text))
    ]


def index_approved_document(document: Document, profile: str | None = None) -> None:
    """Index a committed document. Run this in a worker for production workloads."""
    if not document.staff_approved:
        return
    settings = get_settings()
    profile = profile or settings.embedding_profile
    host = settings.chroma_url.removeprefix("http://").removeprefix("https://")
    hostname, _, port = host.partition(":")
    client = chromadb.HttpClient(host=hostname, port=int(port or 8000), ssl=settings.chroma_url.startswith("https"))
    collection = client.get_or_create_collection(f"approved_knowledge_{profile}", metadata={"hnsw:space": "cosine"})
    texts = [chunk.text for chunk in document.chunks]
    collection.upsert(
        ids=[chunk.chroma_id for chunk in document.chunks if chunk.chroma_id],
        documents=texts,
        embeddings=encode(profile, texts, settings.compute_device),
        metadatas=[
            {"document_id": str(document.id), "course_id": str(document.course_id or "global"), "title": document.title}
            for _ in document.chunks
        ],
    )
