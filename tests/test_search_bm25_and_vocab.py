"""BM25 and vocabulary tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import uuid

from backend.app.schemas import SearchHit
from backend.app.services.bm25 import BM25Document, bm25_rank, tokenize
from backend.app.services.search_ranking import HybridRanker
from backend.app.services.vocabulary import vocabulary_text


def test_bm25_ranks_matching_documents_first() -> None:
    """A query term match receives a positive BM25 score."""
    wanted = uuid.uuid4()
    hits = bm25_rank("microprocessor m3", [
        BM25Document(id=wanted, title="Apple M3", text="Apple M3 microprocessor architecture"),
        BM25Document(id=uuid.uuid4(), title="History", text="German history after 1949"),
    ])
    assert hits[0].id == wanted
    assert hits[0].score > 0


def test_hybrid_ranker_accepts_bm25_channel() -> None:
    """BM25 can be fused with full-text and semantic channels."""
    item_id = uuid.uuid4()
    hits = HybridRanker.fuse(
        {"bm25": [SearchHit(kind="document", id=item_id, title="CPU", excerpt="cpu", score=2.0)]},
        {"full_text": 0.3, "bm25": 0.2, "semantic": 0.5},
    )
    assert hits[0].score_components["bm25"] == 0.2


def test_vocabulary_text_renders_one_token_per_line() -> None:
    """JSON vocabulary bundles can become classic vocab.txt files."""
    assert vocabulary_text({"terms": [{"token": "cpu"}, {"token": "m3"}]}) == "cpu\nm3\n"


def test_tokenize_normalizes_unicode_words() -> None:
    """German and English tokens are normalized for lexical models."""
    assert tokenize("Mikroprozessor-Ära M3") == ["mikroprozessor", "ära", "m3"]
