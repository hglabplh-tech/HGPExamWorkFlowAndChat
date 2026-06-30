"""Unit tests for deterministic ASAG signals.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import pytest

from backend.app.services.asag import discipline_slug, jaccard, keyword_coverage, length_adequacy


def test_jaccard_is_case_insensitive_and_handles_empty_answers() -> None:
    """Lexical similarity uses normalized Unicode word tokens."""
    assert jaccard("CPU and GPU", "cpu and memory") == pytest.approx(0.5)
    assert jaccard("", "") == 1.0


def test_keyword_and_length_signals_are_bounded() -> None:
    """Coverage and length signals remain in the expected zero-to-one range."""
    assert keyword_coverage("Shared CPU and GPU memory", ["CPU", "GPU", "cache"]) == pytest.approx(2 / 3)
    assert keyword_coverage("anything", []) is None
    assert length_adequacy("one two three four", "one two") == 1.0
    assert discipline_slug("German History / 1949+") == "german-history-1949"
