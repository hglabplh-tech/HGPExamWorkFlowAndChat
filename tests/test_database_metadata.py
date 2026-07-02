"""Database-layer contract tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from backend.app.db_models import Base


def test_required_workflow_tables_are_registered() -> None:
    """The ORM exposes every persistent layer needed by the workflows."""
    required = {
        "users", "courses", "documents", "examinations", "exam_questions",
        "submissions", "grade_events", "conversations", "messages",
        "audit_events", "training_examples", "trust_lists", "submission_confirmations",
        "exam_groups", "exam_rule_sets", "thesauri", "active_user_sessions",
        "research_histories", "research_history_entries",
    }
    assert required <= set(Base.metadata.tables)


def test_thesaurus_columns_exist() -> None:
    """Full-text thesauri are stored as JSON and can be activated globally."""
    columns = set(Base.metadata.tables["thesauri"].columns.keys())
    assert {
        "name", "language", "source_format", "entries", "source_sha256",
        "active", "created_by", "created_at",
    } <= columns


def test_submission_retention_and_signature_columns_exist() -> None:
    """Exam records include evidence, legal-hold, deletion, and return fields."""
    columns = set(Base.metadata.tables["submissions"].columns.keys())
    assert {
        "content_sha256", "student_signature", "student_certificate_pem",
        "retention_until", "legal_hold", "deleted_by", "deletion_reason",
        "instructor_signature", "instructor_certificate_pem", "report_sha256",
        "correction_until", "supersedes_submission_id",
        "academic_integrity_review",
        "exam_group_id", "group_certificate_pem",
    } <= columns


def test_user_permissions_are_persisted() -> None:
    """Store explicit grants in addition to the user's base role."""
    assert "permissions" in Base.metadata.tables["users"].columns


def test_user_matriculation_number_is_persisted() -> None:
    """Administrative user masks can store the student's matriculation number."""
    assert "matriculation_number" in Base.metadata.tables["users"].columns


def test_chat_message_attachments_are_persisted() -> None:
    """Chat uploads store safe metadata/transcripts for receivers."""
    assert "attachments" in Base.metadata.tables["messages"].columns


def test_totp_columns_are_persisted() -> None:
    """Users can opt into authenticator-app two-factor login."""
    columns = set(Base.metadata.tables["users"].columns.keys())
    assert {"totp_secret", "totp_enabled"} <= columns


def test_active_user_session_columns_are_persisted() -> None:
    """Every login is backed by a revocable session row."""
    columns = set(Base.metadata.tables["active_user_sessions"].columns.keys())
    assert {
        "user_id", "token_sha256", "client_cert_fingerprint", "issued_at",
        "expires_at", "last_seen_at", "revoked_at", "auth_method",
        "request_metadata",
    } <= columns


def test_research_history_tables_are_persisted() -> None:
    """Research histories can label, store, and replay user-scoped context."""
    history_columns = set(Base.metadata.tables["research_histories"].columns.keys())
    entry_columns = set(Base.metadata.tables["research_history_entries"].columns.keys())
    assert {"user_id", "active_session_id", "label", "stored", "deleted_at", "updated_at"} <= history_columns
    assert {"history_id", "kind", "input_text", "refined_text", "output_summary", "payload"} <= entry_columns
