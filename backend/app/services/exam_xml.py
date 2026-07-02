"""Secure versioned XML import and export for course examinations.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import json
from xml.etree.ElementTree import Element, ParseError, SubElement, tostring

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException


FORMAT = "hgp-exam-work-flow-and-chat/exam-v1"


def export_exam_xml(course_code: str, exam: object, questions: list[object], rules: dict | None = None) -> bytes:
    """Serialize an examination without private answers or submission evidence."""
    root = Element("examination", {"format": FORMAT, "course-code": course_code})
    SubElement(root, "title").text = str(exam.title)
    SubElement(root, "instructions").text = str(exam.instructions or "")
    SubElement(root, "kind").text = str(exam.kind)
    SubElement(root, "group-mode").text = "true" if exam.group_mode else "false"
    if rules:
        SubElement(root, "rules-json").text = json.dumps(rules, sort_keys=True)
    question_root = SubElement(root, "questions")
    for question in questions:
        node = SubElement(question_root, "question", {"type": question.question_type, "max-score": str(question.max_score), "partial-credit": str(question.partial_credit).lower()})
        SubElement(node, "prompt").text = question.prompt
        SubElement(node, "reference-answer").text = question.reference_answer
        for value in question.required_keywords:
            SubElement(node, "keyword").text = str(value)
        for value in question.expected_facts:
            SubElement(node, "fact").text = str(value)
        for value in question.choices:
            option = SubElement(node, "choice", {"correct": str(value in question.correct_options).lower()})
            option.text = str(value)
    return tostring(root, encoding="utf-8", xml_declaration=True)


def import_exam_xml(data: bytes) -> dict:
    """Parse a bounded defused XML document into validated primitive values."""
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("Exam XML exceeds 5 MiB")
    try:
        root = SafeElementTree.fromstring(data)
    except (ParseError, DefusedXmlException) as error:
        raise ValueError("Malformed or unsafe exam XML") from error
    if root.tag != "examination" or root.attrib.get("format") != FORMAT:
        raise ValueError("Unsupported exam XML format")
    questions = []
    for node in root.findall("./questions/question"):
        choices = [value.text or "" for value in node.findall("choice")]
        correct = [value.text or "" for value in node.findall("choice") if value.attrib.get("correct") == "true"]
        questions.append({
            "prompt": node.findtext("prompt", ""),
            "reference_answer": node.findtext("reference-answer", ""),
            "required_keywords": [value.text or "" for value in node.findall("keyword")],
            "expected_facts": [value.text or "" for value in node.findall("fact")],
            "max_score": float(node.attrib.get("max-score", "0")),
            "question_type": node.attrib.get("type", "free_text"),
            "choices": choices,
            "correct_options": correct,
            "partial_credit": node.attrib.get("partial-credit") == "true",
        })
    if not questions:
        raise ValueError("Exam XML contains no questions")
    return {
        "course_code": root.attrib.get("course-code", ""),
        "title": root.findtext("title", ""),
        "instructions": root.findtext("instructions", ""),
        "kind": root.findtext("kind", "practice"),
        "group_mode": root.findtext("group-mode", "false") == "true",
        "rules": json.loads(root.findtext("rules-json", "null")),
        "questions": questions,
    }
