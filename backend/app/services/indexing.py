# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for indexing."""
from contextlib import suppress
import uuid

import chromadb

from ..config import get_settings
from ..models import Document, DocumentChunk
from .embeddings import encode


def _chroma_client(settings):
    """Create a Chroma HTTP client from configured service URL."""
    host = settings.chroma_url.removeprefix("http://").removeprefix("https://")
    hostname, _, port = host.partition(":")
    return chromadb.HttpClient(
        host=hostname,
        port=int(port or 8000),
        ssl=settings.chroma_url.startswith("https"),
    )


def _collection_name(profile: str) -> str:
    """Return the approved-knowledge Chroma collection name for an embedding profile."""
    return f"approved_knowledge_{profile}"


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
    client = _chroma_client(settings)
    collection = client.get_or_create_collection(_collection_name(profile), metadata={"hnsw:space": "cosine"})
    chunks = [chunk for chunk in document.chunks if chunk.chroma_id and chunk.text]
    texts = [chunk.text for chunk in chunks]
    if not texts:
        return
    collection.upsert(
        ids=[chunk.chroma_id for chunk in chunks],
        documents=texts,
        embeddings=encode(profile, texts, settings.compute_device),
        metadatas=[
            {"document_id": str(document.id), "course_id": str(document.course_id or "global"), "title": document.title}
            for _ in chunks
        ],
    )


def rebuild_chroma_from_documents(documents: list[Document], profile: str | None = None, batch_size: int = 64) -> dict:
    """Reset and rebuild one Chroma approved-knowledge collection from PostgreSQL documents."""
    settings = get_settings()
    profile = profile or settings.embedding_profile
    client = _chroma_client(settings)
    name = _collection_name(profile)
    with suppress(Exception):
        client.delete_collection(name)
    collection = client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
    indexed_chunks = 0
    indexed_documents: set[str] = set()
    for document in documents:
        chunks = [chunk for chunk in document.chunks if chunk.chroma_id and chunk.text]
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            texts = [chunk.text for chunk in batch]
            if not texts:
                continue
            collection.upsert(
                ids=[chunk.chroma_id for chunk in batch],
                documents=texts,
                embeddings=encode(profile, texts, settings.compute_device),
                metadatas=[
                    {"document_id": str(document.id), "course_id": str(document.course_id or "global"), "title": document.title}
                    for _ in batch
                ],
            )
            indexed_chunks += len(batch)
            indexed_documents.add(str(document.id))
    return {
        "collection": name,
        "profile": profile,
        "documents_indexed": len(indexed_documents),
        "chunks_indexed": indexed_chunks,
    }
