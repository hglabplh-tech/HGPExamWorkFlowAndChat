"""Unit tests for deterministic ASAG signals.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import pytest

from backend.app.services.asag import (
    ASAG_FORMULA_WEIGHTS,
    bm25_keyword_coverage,
    discipline_slug,
    fixed_asag_score,
    jaccard,
    keyword_coverage,
    length_adequacy,
    resolve_asag_weights,
)
from backend.app.db_models.examinations import DisciplineScoringProfile


def test_jaccard_is_case_insensitive_and_handles_empty_answers() -> None:
    """Lexical similarity uses normalized Unicode word tokens."""
    assert jaccard("CPU and GPU", "cpu and memory") == pytest.approx(0.5)
    assert jaccard("", "") == 1.0


def test_keyword_and_length_signals_are_bounded() -> None:
    """Coverage and length signals remain in the expected zero-to-one range."""
    assert keyword_coverage("Shared CPU and GPU memory", ["CPU", "GPU", "cache"]) == pytest.approx(2 / 3)
    assert bm25_keyword_coverage("Shared CPU and GPU memory", ["CPU", "GPU", "cache"]) == pytest.approx(2 / 3)
    assert keyword_coverage("anything", []) is None
    assert length_adequacy("one two three four", "one two") == 1.0
    assert discipline_slug("German History / 1949+") == "german-history-1949"


def test_fixed_asag_formula_uses_requested_weights() -> None:
    """The ASAG score follows the requested BERT/embedding/lexical/context formula."""
    signals = {
        "cross_encoder": 0.96,
        "embedding_similarity": 0.94,
        "jaccard": 0.50,
        "bm25": 1.0,
        "context_match": 0.94,
        "fact_coverage": 0.92,
    }
    score, weights, warnings = fixed_asag_score(signals)
    assert weights == ASAG_FORMULA_WEIGHTS
    assert warnings == []
    assert score == pytest.approx(0.909)


def test_asag_weights_can_fall_back_override_and_use_topic() -> None:
    """Weights fall back globally and can be configured per discipline or topic."""
    assert resolve_asag_weights(None) == ASAG_FORMULA_WEIGHTS
    profile = DisciplineScoringProfile(
        discipline="Computer Science",
        version=1,
        semantic_profile="economy",
        grading_weights={
            "default": {"cross_encoder": 0.50, "embedding_similarity": 0.20},
            "topics": {
                "Apple M3 / Hardware": {"cross_encoder": 0.55, "bm25": 0.15},
            },
        },
    )
    discipline_weights = resolve_asag_weights(profile)
    topic_weights = resolve_asag_weights(profile, "Apple M3 / Hardware")
    assert discipline_weights["cross_encoder"] == pytest.approx(0.50)
    assert discipline_weights["embedding_similarity"] == pytest.approx(0.20)
    assert sum(discipline_weights.values()) == pytest.approx(1.0)
    assert topic_weights["cross_encoder"] == pytest.approx(0.55)
    assert topic_weights["bm25"] == pytest.approx(0.15)
    assert sum(topic_weights.values()) == pytest.approx(1.0)
