# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for test indexing."""
from backend.app.services.indexing import split_text


def test_split_text_preserves_overlap_and_tail():
    """Verify split text preserves overlap and tail."""
    text = "a" * 2200
    chunks = split_text(text, size=1000, overlap=100)
    assert [len(chunk) for chunk in chunks] == [1000, 1000, 400]


def test_empty_text_has_no_chunks():
    """Verify empty text has no chunks."""
    assert split_text("   ") == []

