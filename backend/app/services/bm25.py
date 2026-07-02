# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Small dependency-free BM25 retrieval utilities for approved knowledge chunks."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from ..schemas import SearchHit


TOKEN_RE = re.compile(r"[\wÄÖÜäöüß]+", re.UNICODE)


@dataclass(frozen=True)
class BM25Document:
    """Represent one searchable document chunk for BM25 scoring."""

    id: UUID
    title: str
    text: str


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase word tokens for BM25 and vocabulary generation."""
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def bm25_rank(
    query: str,
    documents: list[BM25Document],
    *,
    limit: int = 10,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[SearchHit]:
    """Rank documents with Okapi BM25 and return search hits."""
    query_terms = tokenize(query)
    if not query_terms or not documents:
        return []
    tokenized = [tokenize(item.text) for item in documents]
    average_length = sum(len(tokens) for tokens in tokenized) / max(1, len(tokenized))
    document_frequency = Counter(term for tokens in tokenized for term in set(tokens))
    ranked: list[SearchHit] = []
    for item, tokens in zip(documents, tokenized, strict=True):
        counts = Counter(tokens)
        score = 0.0
        length = len(tokens) or 1
        for term in query_terms:
            if not counts[term]:
                continue
            idf = math.log(1 + (len(documents) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            denominator = counts[term] + k1 * (1 - b + b * length / max(1.0, average_length))
            score += idf * counts[term] * (k1 + 1) / denominator
        if score > 0:
            ranked.append(SearchHit(kind="document", id=item.id, title=item.title, excerpt=item.text[:500], score=score))
    return sorted(ranked, key=lambda hit: hit.score, reverse=True)[:limit]
