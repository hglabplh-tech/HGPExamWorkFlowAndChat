"""Microbenchmarks for pure hot-path utilities.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import uuid

from backend.app.schemas import SearchHit
from backend.app.services.asag import jaccard
from backend.app.services.ingestion import ContentExtractor, answer_from_uploaded_text
from backend.app.services.search_ranking import HybridRanker


def test_jaccard_performance(benchmark) -> None:
    """Measure deterministic lexical scoring throughput."""
    result = benchmark(jaccard, "CPU GPU unified memory synchronization", "GPU CPU shared memory")
    assert 0 <= result <= 1


def test_text_extraction_performance(benchmark) -> None:
    """Measure plain-text normalization and hashing throughput."""
    result = benchmark(ContentExtractor.extract, ("A sentence. " * 1000).encode(), "text/plain", "sample.txt")
    assert result.sha256


def test_upload_question_performance(benchmark) -> None:
    """Measure extractive relevance selection for file-and-question requests."""
    result = benchmark(answer_from_uploaded_text, "What is unified memory?", "Unified memory is shared.\n\nA GPU executes parallel work.")
    assert result["passages"]


def test_hybrid_fusion_performance(benchmark) -> None:
    """Measure weighted fusion over representative retrieval channels."""
    hits = [SearchHit(kind="document", id=uuid.uuid4(), title="T", excerpt="E", score=(i + 1) / 100) for i in range(100)]
    result = benchmark(HybridRanker.fuse, {"full_text": hits, "semantic": hits}, {"full_text": 0.4, "semantic": 0.6})
    assert len(result) == 100
