"""Database-layer contract tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from backend.app.db_models import Base


def test_required_workflow_tables_are_registered() -> None:
    """The ORM exposes every persistent layer needed by the workflows."""
    required = {
        "users", "courses", "documents", "examinations", "exam_questions",
        "submissions", "grade_events", "conversations", "messages",
        "audit_events", "training_examples", "trust_lists",
    }
    assert required <= set(Base.metadata.tables)


def test_submission_retention_and_signature_columns_exist() -> None:
    """Exam records include evidence, legal-hold, deletion, and return fields."""
    columns = set(Base.metadata.tables["submissions"].columns.keys())
    assert {
        "content_sha256", "student_signature", "student_certificate_pem",
        "retention_until", "legal_hold", "deleted_by", "deletion_reason",
        "instructor_signature", "instructor_certificate_pem", "report_sha256",
    } <= columns
