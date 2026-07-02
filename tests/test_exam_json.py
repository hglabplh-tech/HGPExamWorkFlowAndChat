"""Exam JSON import/export tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from types import SimpleNamespace

import pytest

from backend.app.schemas import ExaminationJsonCreate
from backend.app.services.exam_json import FORMAT, export_exam_json, import_exam_json


def test_exam_json_round_trip_preserves_questions_and_points() -> None:
    """The instructor JSON format stores prompts, reference answers, and points."""
    exam = SimpleNamespace(title="M3 Exam", instructions="Answer all", kind="practice", group_mode=False)
    question = SimpleNamespace(
        prompt="Explain the M3 performance core.",
        reference_answer="It is a CPU core optimized for high performance.",
        required_keywords=["CPU"],
        expected_facts=["M3 contains performance cores."],
        max_score=12.5,
        question_type="free_text",
        choices=[],
        correct_options=[],
        partial_credit=False,
    )
    payload = export_exam_json("CS-M3", exam, [question])
    parsed = import_exam_json(payload)
    assert payload["format"] == FORMAT
    assert parsed["course_code"] == "CS-M3"
    assert parsed["questions"][0]["max_score"] == 12.5
    assert parsed["questions"][0]["reference_answer"].startswith("It is a CPU")


def test_exam_json_rejects_empty_question_files() -> None:
    """An exam JSON file must contain at least one question."""
    with pytest.raises(ValueError):
        import_exam_json({"format": FORMAT, "title": "Empty", "questions": []})


def test_exam_json_schema_validates_nested_choice_questions() -> None:
    """The one-call exam creation schema validates nested answer keys."""
    data = ExaminationJsonCreate(
        title="Choice exam",
        questions=[{
            "prompt": "Pick one",
            "reference_answer": "A",
            "max_score": 1,
            "question_type": "single_choice",
            "choices": ["A", "B"],
            "correct_options": ["A"],
        }],
    )
    data.validate_exam()
    with pytest.raises(ValueError):
        ExaminationJsonCreate(
            title="Bad choice",
            questions=[{
                "prompt": "Pick one",
                "reference_answer": "A",
                "max_score": 1,
                "question_type": "single_choice",
                "choices": ["A", "B"],
                "correct_options": ["C"],
            }],
        ).validate_exam()
