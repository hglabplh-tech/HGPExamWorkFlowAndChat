-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.

CREATE TABLE IF NOT EXISTS exam_rule_sets (
    id uuid PRIMARY KEY,
    course_id uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    name varchar(200) NOT NULL,
    version integer NOT NULL,
    rules jsonb NOT NULL,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(course_id, name, version)
);
CREATE INDEX IF NOT EXISTS ix_exam_rule_sets_course_id ON exam_rule_sets(course_id);

ALTER TABLE examinations ADD COLUMN IF NOT EXISTS group_mode boolean NOT NULL DEFAULT false;
ALTER TABLE examinations ADD COLUMN IF NOT EXISTS rule_set_id uuid REFERENCES exam_rule_sets(id);

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS purpose varchar(40) NOT NULL DEFAULT 'general';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS topic varchar(300);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS examination_id uuid REFERENCES examinations(id);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS random_assignment_seed varchar(128);
CREATE INDEX IF NOT EXISTS ix_conversations_purpose ON conversations(purpose);
CREATE INDEX IF NOT EXISTS ix_conversations_examination_id ON conversations(examination_id);

CREATE TABLE IF NOT EXISTS exam_groups (
    id uuid PRIMARY KEY,
    examination_id uuid NOT NULL REFERENCES examinations(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL UNIQUE REFERENCES conversations(id) ON DELETE CASCADE,
    label varchar(120) NOT NULL,
    topic varchar(300) NOT NULL,
    certificate_pem bytea,
    certificate_sha256 varchar(64) UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(examination_id, conversation_id)
);
CREATE INDEX IF NOT EXISTS ix_exam_groups_examination_id ON exam_groups(examination_id);

ALTER TABLE exam_questions ADD COLUMN IF NOT EXISTS question_type varchar(30) NOT NULL DEFAULT 'free_text';
ALTER TABLE exam_questions ADD COLUMN IF NOT EXISTS choices jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE exam_questions ADD COLUMN IF NOT EXISTS correct_options jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE exam_questions ADD COLUMN IF NOT EXISTS partial_credit boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS ix_exam_questions_question_type ON exam_questions(question_type);

ALTER TABLE submissions ADD COLUMN IF NOT EXISTS exam_group_id uuid REFERENCES exam_groups(id);
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS group_certificate_pem bytea;
CREATE INDEX IF NOT EXISTS ix_submissions_exam_group_id ON submissions(exam_group_id);
