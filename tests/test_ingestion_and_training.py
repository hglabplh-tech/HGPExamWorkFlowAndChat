"""Tests for content ingestion and shortcut-mitigation utilities.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import uuid

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.schemas import SubmissionPrepare
from backend.app.services.ingestion import ContentExtractor, answer_from_uploaded_text
from ml.train_bert import restructure_sentences
from ml.train_lstm import shuffled_sentences


def test_text_ingestion_is_content_addressed_and_normalized() -> None:
    """Ensure equivalent normalized UTF-8 inputs have one stable hash."""
    first = ContentExtractor.extract(b"A   line.\r\nSecond line.", "text/plain", "a.txt")
    second = ContentExtractor.extract(b"A line.\nSecond line.", "text/plain", "b.txt")
    assert first.sha256 == second.sha256
    assert first.text == "A line.\nSecond line."


def test_upload_question_selects_relevant_context() -> None:
    """Ensure question terms prioritize the matching upload passage."""
    result = answer_from_uploaded_text("What is unified memory?", "A GPU runs kernels.\n\nUnified memory is shared by CPU and GPU.")
    assert result["passages"][0].startswith("Unified memory")


def test_shortcut_mitigation_is_seeded_and_reproducible() -> None:
    """Ensure sentence restructuring is repeatable for audited runs."""
    text = "First sentence. Second sentence. Third sentence."
    assert restructure_sentences(text, 42) == restructure_sentences(text, 42)
    assert shuffled_sentences(text, 42) == shuffled_sentences(text, 42)


def test_model_allowlist_and_submission_hash_validation() -> None:
    """Reject unapproved models and malformed confirmation hashes."""
    settings = Settings()
    assert settings.require_allowed_model(settings.audio_model) == settings.audio_model
    with pytest.raises(ValueError):
        settings.require_allowed_model("unreviewed/premium-model")
    with pytest.raises(ValidationError):
        SubmissionPrepare(examination_id=uuid.uuid4(), content_sha256="bad")
