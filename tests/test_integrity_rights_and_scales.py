"""Tests for integrity evidence, RBAC permissions, and grading conversions.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import pytest

from backend.app.models import Role, User
from backend.app.services.academic_integrity import candidate_passages, check_apa_citations
from backend.app.services.authorization import has_permission, validate_permissions
from backend.app.services.grading_scales import EUROPEAN_ECTS_COUNTRIES, convert_grades


def test_apa_review_detects_author_year_and_references() -> None:
    """Detect basic APA evidence without asserting academic misconduct."""
    review = check_apa_citations("Smith (2024) explains the result.\n\nReferences\nSmith, A. (2024). A title.")
    assert review["citation_count"] == 1
    assert review["has_reference_section"]
    assert not review["warnings"]


def test_candidate_passages_prioritize_substantial_sentences() -> None:
    """Use substantial passages rather than tiny fragments for Internet queries."""
    passages = candidate_passages("Short. This is a sufficiently substantial sentence for a similarity search query.")
    assert len(passages) == 1
    assert passages[0].startswith("This is")


def test_roles_and_explicit_permissions_are_combined() -> None:
    """Administrative, instructor, and explicit user grants compose predictably."""
    teacher = User(role=Role.teacher, permissions=[])
    student = User(role=Role.student, permissions=["email.send"])
    assert has_permission(teacher, "grading.manage")
    assert has_permission(student, "email.send")
    with pytest.raises(ValueError):
        validate_permissions(["invented.right"])


def test_grading_conversions_cover_ects_german_british_us_and_europe() -> None:
    """Return indicative conversions with an institutional-scale disclaimer."""
    result = convert_grades(85, 100)
    assert result["ects"] == "B"
    assert result["germany"] == "1.7"
    assert result["united_kingdom"].startswith("First")
    assert result["united_states"] == {"letter": "B", "gpa_4": "3.0"}
    assert set(result["european_country_ects"]) == EUROPEAN_ECTS_COUNTRIES
    assert "institution" in result["disclaimer"]
