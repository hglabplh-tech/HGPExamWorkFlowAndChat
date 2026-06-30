"""Unit tests for hybrid ranking.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import uuid

import pytest

from backend.app.schemas import SearchHit
from backend.app.services.search_ranking import HybridRanker


def hit(identifier: uuid.UUID, score: float) -> SearchHit:
    """Build a minimal document search hit."""
    return SearchHit(kind="document", id=identifier, title="T", excerpt="E", score=score)


def test_weights_are_normalized_and_invalid_weights_rejected() -> None:
    """Weights must be normalized and contain a positive channel."""
    assert HybridRanker.normalize_weights({"full_text": 2, "semantic": 1}) == pytest.approx(
        {"full_text": 2 / 3, "semantic": 1 / 3}
    )
    with pytest.raises(ValueError):
        HybridRanker.normalize_weights({"full_text": 0, "semantic": 0})
    with pytest.raises(ValueError):
        HybridRanker.normalize_weights({"full_text": -1, "semantic": 2})


def test_fusion_combines_duplicate_hits_and_orders_results() -> None:
    """A hit present in both channels receives both contributions."""
    shared, lexical_only = uuid.uuid4(), uuid.uuid4()
    result = HybridRanker.fuse(
        {
            "full_text": [hit(shared, 1.0), hit(lexical_only, 0.8)],
            "semantic": [hit(shared, 0.5)],
        },
        {"full_text": 0.4, "semantic": 0.6},
    )
    assert result[0].id == shared
    assert result[0].score == pytest.approx(1.0)
    assert result[0].score_components == {"full_text": 0.4, "semantic": 0.6}
