-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Course knowledge-base entry points and encrypted examination/scoring payloads.

CREATE TABLE IF NOT EXISTS course_knowledge_bases (
    id uuid PRIMARY KEY,
    course_id uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    name varchar(160) NOT NULL DEFAULT 'default',
    description text NOT NULL DEFAULT '',
    fulltext_config varchar(80) NOT NULL DEFAULT 'simple',
    semantic_profile varchar(20) NOT NULL DEFAULT 'economy',
    mbert_model varchar(300),
    active boolean NOT NULL DEFAULT true,
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(course_id, name)
);

CREATE INDEX IF NOT EXISTS ix_course_knowledge_bases_course_id ON course_knowledge_bases(course_id);
CREATE INDEX IF NOT EXISTS ix_course_knowledge_bases_active ON course_knowledge_bases(active);

ALTER TABLE submissions ADD COLUMN IF NOT EXISTS encrypted_answers jsonb;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS encrypted_content jsonb;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS encrypted_ai_grade jsonb;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS encrypted_teacher_grade jsonb;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS encryption_recipients jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS encryption_status varchar(40) NOT NULL DEFAULT 'pending';

ALTER TABLE grade_events ADD COLUMN IF NOT EXISTS encrypted_grade jsonb;

ALTER TABLE messages ADD COLUMN IF NOT EXISTS mentioned_user_ids jsonb NOT NULL DEFAULT '[]'::jsonb;
