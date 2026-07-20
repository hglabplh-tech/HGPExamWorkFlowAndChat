# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Versioned JSON import and export for instructor-created examinations."""

import json


FORMAT = "hgp-exam-work-flow-and-chat/exam-json-v1"


def export_exam_json(course_code: str, exam: object, questions: list[object]) -> dict:
    """Serialize an examination draft to the reviewable JSON exam format."""
    return {
        "format": FORMAT,
        "course_code": course_code,
        "title": exam.title,
        "instructions": exam.instructions or "",
        "kind": exam.kind,
        "group_mode": bool(exam.group_mode),
        "questions": [
            {
                "prompt": question.prompt,
                "reference_answer": question.reference_answer,
                "required_keywords": question.required_keywords,
                "expected_facts": question.expected_facts,
                "max_score": question.max_score,
                "question_type": question.question_type,
                "question_category": getattr(question, "question_category", "description"),
                "choices": question.choices,
                "correct_options": question.correct_options,
                "partial_credit": question.partial_credit,
            }
            for question in questions
        ],
    }


def import_exam_json(data: bytes | str | dict) -> dict:
    """Parse bounded JSON into primitive exam values."""
    if isinstance(data, bytes):
        if len(data) > 5 * 1024 * 1024:
            raise ValueError("Exam JSON exceeds 5 MiB")
        payload = json.loads(data.decode("utf-8"))
    elif isinstance(data, str):
        if len(data.encode("utf-8")) > 5 * 1024 * 1024:
            raise ValueError("Exam JSON exceeds 5 MiB")
        payload = json.loads(data)
    else:
        payload = data
    if not isinstance(payload, dict) or payload.get("format", FORMAT) != FORMAT:
        raise ValueError("Unsupported exam JSON format")
    questions = payload.get("questions", [])
    if not isinstance(questions, list) or not questions:
        raise ValueError("Exam JSON contains no questions")
    return {
        "course_code": payload.get("course_code", ""),
        "title": payload.get("title", ""),
        "instructions": payload.get("instructions", ""),
        "kind": payload.get("kind", "practice"),
        "group_mode": bool(payload.get("group_mode", False)),
        "rule_set_id": payload.get("rule_set_id"),
        "questions": questions,
    }
