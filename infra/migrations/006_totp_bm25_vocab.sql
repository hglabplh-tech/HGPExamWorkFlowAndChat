-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Add two-factor login support and document BM25/search-vocabulary rollout.

ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret varchar(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled boolean NOT NULL DEFAULT false;
