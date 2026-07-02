-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Store metadata, transcripts, and safe text previews for chat attachments.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS attachments jsonb NOT NULL DEFAULT '[]'::jsonb;
