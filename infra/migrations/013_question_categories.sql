-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Add ASAG/RPC-over-HTTP question categories for exam scoring and reporting.

ALTER TABLE exam_questions ADD COLUMN IF NOT EXISTS question_category varchar(30) NOT NULL DEFAULT 'description';

CREATE INDEX IF NOT EXISTS ix_exam_questions_question_category ON exam_questions(question_category);
