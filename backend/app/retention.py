RETENTION_DDL = [
    """
    CREATE OR REPLACE FUNCTION protect_submission_evidence() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'physical deletion of examination evidence is forbidden';
      END IF;
      IF NEW.content IS DISTINCT FROM OLD.content
         OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
         OR NEW.student_signature IS DISTINCT FROM OLD.student_signature
         OR NEW.student_id IS DISTINCT FROM OLD.student_id
         OR NEW.examination_id IS DISTINCT FROM OLD.examination_id
         OR NEW.client_signed_at IS DISTINCT FROM OLD.client_signed_at
         OR NEW.receipt_nonce IS DISTINCT FROM OLD.receipt_nonce
         OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at THEN
        RAISE EXCEPTION 'signed examination evidence is immutable';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS submission_evidence_guard ON submissions",
    """
    CREATE TRIGGER submission_evidence_guard
    BEFORE UPDATE OR DELETE ON submissions
    FOR EACH ROW EXECUTE FUNCTION protect_submission_evidence()
    """,
    """
    CREATE OR REPLACE FUNCTION immutable_audit_events() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'audit events are append-only';
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS audit_event_guard ON audit_events",
    """
    CREATE TRIGGER audit_event_guard
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION immutable_audit_events()
    """,
    "DROP TRIGGER IF EXISTS grade_event_guard ON grade_events",
    """
    CREATE TRIGGER grade_event_guard
    BEFORE UPDATE OR DELETE ON grade_events
    FOR EACH ROW EXECUTE FUNCTION immutable_audit_events()
    """,
]
