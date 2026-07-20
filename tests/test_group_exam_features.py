"""Tests for random groups, exam rules, multiple choice, and XML exchange.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import uuid
from types import SimpleNamespace

import pytest

from backend.app.schemas import ExamRuleSetCreate, QuestionCreate
from backend.app.services.exam_rules import evaluate_exam_rules
from backend.app.services.exam_xml import export_exam_xml, import_exam_xml
from backend.app.services.exam_json import export_exam_json, import_exam_json
from backend.app.services.group_assignment import assign_random_groups
from backend.app.services.multiple_choice import score_choice_answer


def test_random_groups_are_seeded_balanced_and_complete() -> None:
    """Assign every student exactly once without a singleton remainder."""
    students = [uuid.uuid4() for _ in range(7)]
    first = assign_random_groups(students, 3, "audit-seed")
    second = assign_random_groups(students, 3, "audit-seed")
    assert first == second
    assert sorted(member for group in first for member in group) == sorted(students)
    assert max(map(len, first)) <= 3 and min(map(len, first)) >= 2


def test_choice_scoring_supports_exact_and_penalized_partial_credit() -> None:
    """Score single/multiple choices with bounded wrong-option penalties."""
    assert score_choice_answer(["A", "C"], ["A", "C"], 10, True)["score"] == 10
    assert score_choice_answer(["A", "B"], ["A", "C"], 10, True)["score"] == 0
    assert score_choice_answer("A", ["A"], 5, False)["exact_match"]


def test_exam_rules_validate_and_produce_weighted_signals() -> None:
    """Validate rule weights and expose each review dimension."""
    rules = ExamRuleSetCreate(course_id=uuid.uuid4(), name="Essay", topic="microprocessor architecture")
    rules.validate_rules()
    result = evaluate_exam_rules("Microprocessor architecture provides context.\n\nSmith (2024) explains it.\n\nReferences", rules.model_dump())
    assert set(result["signals"]) == {"context", "design", "wording", "citations"}
    with pytest.raises(ValueError):
        ExamRuleSetCreate(course_id=uuid.uuid4(), name="Bad", topic="x", weights={"context": 1}).validate_rules()


def test_exam_xml_round_trip_preserves_mcq_and_rejects_unsafe_format() -> None:
    """Round-trip versioned exam XML without submissions or private evidence."""
    exam = SimpleNamespace(title="M3 Exam", instructions="Answer all", kind="practice", group_mode=True)
    question = SimpleNamespace(
        question_type="multiple_choice", max_score=10, partial_credit=True,
        question_category="fact",
        prompt="Select components", reference_answer="CPU and GPU",
        required_keywords=["SoC"], expected_facts=["M3 is a SoC"],
        choices=["CPU", "GPU", "Printer"], correct_options=["CPU", "GPU"],
    )
    parsed = import_exam_xml(export_exam_xml("CS-M3", exam, [question], {"topic": "M3"}))
    assert parsed["group_mode"] and parsed["questions"][0]["correct_options"] == ["CPU", "GPU"]
    assert parsed["questions"][0]["question_category"] == "fact"
    with pytest.raises(ValueError):
        import_exam_xml(b"<examination format='unknown'/>")


def test_exam_json_exchange_preserves_reference_answers() -> None:
    """Round-trip versioned exam JSON for GUI-created question-answer exams."""
    exam = SimpleNamespace(title="History Exam", instructions="Explain", kind="practice", group_mode=False)
    question = SimpleNamespace(
        question_type="free_text", max_score=8, partial_credit=False,
        question_category="argument",
        prompt="What happened in 1949?", reference_answer="The Federal Republic of Germany was founded.",
        required_keywords=["Federal Republic"], expected_facts=["The FRG was founded in 1949."],
        choices=[], correct_options=[],
    )
    parsed = import_exam_json(export_exam_json("HIST-1949", exam, [question]))
    assert parsed["questions"][0]["reference_answer"].startswith("The Federal")
    assert parsed["questions"][0]["question_category"] == "argument"


def test_choice_question_schema_rejects_unknown_correct_options() -> None:
    """Prevent invalid answer keys from entering PostgreSQL or XML imports."""
    question = QuestionCreate(prompt="Pick", reference_answer="A", max_score=1, question_type="single_choice", choices=["A", "B"], correct_options=["C"])
    with pytest.raises(ValueError):
        question.validate_question()
