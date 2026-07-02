-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Add optional student matriculation numbers for administration masks.

ALTER TABLE users ADD COLUMN IF NOT EXISTS matriculation_number varchar(80);
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_matriculation_number ON users(matriculation_number) WHERE matriculation_number IS NOT NULL;
