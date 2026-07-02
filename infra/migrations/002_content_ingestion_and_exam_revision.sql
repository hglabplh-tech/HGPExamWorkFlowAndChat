-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Apply once to databases created before content-addressed ingestion was introduced.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_sha256 varchar(64);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS media_type varchar(120) NOT NULL DEFAULT 'text/plain';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS imported_at timestamptz NOT NULL DEFAULT now();
UPDATE documents SET content_sha256 = encode(digest(body_text, 'sha256'), 'hex') WHERE content_sha256 IS NULL;
ALTER TABLE documents ALTER COLUMN content_sha256 SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_content_sha256 ON documents(content_sha256);

ALTER TABLE submissions ADD COLUMN IF NOT EXISTS correction_until timestamptz;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS supersedes_submission_id uuid REFERENCES submissions(id);

CREATE TABLE IF NOT EXISTS submission_confirmations (
    id uuid PRIMARY KEY,
    examination_id uuid NOT NULL REFERENCES examinations(id),
    student_id uuid NOT NULL REFERENCES users(id),
    content_sha256 varchar(64) NOT NULL,
    token_sha256 varchar(64) NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_submission_confirmations_examination_id ON submission_confirmations(examination_id);
CREATE INDEX IF NOT EXISTS ix_submission_confirmations_student_id ON submission_confirmations(student_id);
CREATE INDEX IF NOT EXISTS ix_submission_confirmations_expires_at ON submission_confirmations(expires_at);
