-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Persist active login sessions so bearer tokens can be invalidated by logout.

CREATE TABLE IF NOT EXISTS active_user_sessions (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_sha256 varchar(64) NOT NULL UNIQUE,
    client_cert_fingerprint varchar(128),
    issued_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    last_seen_at timestamptz,
    revoked_at timestamptz,
    auth_method varchar(40) NOT NULL DEFAULT 'password_totp',
    request_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_active_user_sessions_user_id ON active_user_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_active_user_sessions_token_sha256 ON active_user_sessions(token_sha256);
CREATE INDEX IF NOT EXISTS ix_active_user_sessions_client_cert_fingerprint ON active_user_sessions(client_cert_fingerprint);
CREATE INDEX IF NOT EXISTS ix_active_user_sessions_expires_at ON active_user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS ix_active_user_sessions_revoked_at ON active_user_sessions(revoked_at);
