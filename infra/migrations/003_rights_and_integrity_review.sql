-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.

ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS academic_integrity_review jsonb;
