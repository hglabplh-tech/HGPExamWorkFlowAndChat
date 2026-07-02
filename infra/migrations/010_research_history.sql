-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Store per-user research histories attached to active login sessions.

CREATE TABLE IF NOT EXISTS research_histories (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    active_session_id uuid REFERENCES active_user_sessions(id) ON DELETE SET NULL,
    label varchar(160) NOT NULL DEFAULT 'New chat',
    stored boolean NOT NULL DEFAULT false,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS research_history_entries (
    id uuid PRIMARY KEY,
    history_id uuid NOT NULL REFERENCES research_histories(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id uuid REFERENCES courses(id),
    kind varchar(40) NOT NULL,
    label varchar(160),
    input_text text NOT NULL,
    refined_text text,
    output_summary text NOT NULL DEFAULT '',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_research_histories_user_id ON research_histories(user_id);
CREATE INDEX IF NOT EXISTS ix_research_histories_active_session_id ON research_histories(active_session_id);
CREATE INDEX IF NOT EXISTS ix_research_histories_stored ON research_histories(stored);
CREATE INDEX IF NOT EXISTS ix_research_histories_deleted_at ON research_histories(deleted_at);
CREATE INDEX IF NOT EXISTS ix_research_history_entries_history_id ON research_history_entries(history_id);
CREATE INDEX IF NOT EXISTS ix_research_history_entries_user_id ON research_history_entries(user_id);
CREATE INDEX IF NOT EXISTS ix_research_history_entries_course_id ON research_history_entries(course_id);
CREATE INDEX IF NOT EXISTS ix_research_history_entries_kind ON research_history_entries(kind);
