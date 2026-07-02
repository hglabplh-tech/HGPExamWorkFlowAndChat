-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Add user-owned contact data, registration activation, and TOTP delivery preferences.

ALTER TABLE users ADD COLUMN IF NOT EXISTS contact_email varchar(320);
ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_number varchar(40);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_verified boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_delivery_channel varchar(12) NOT NULL DEFAULT 'email';
ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_completed boolean NOT NULL DEFAULT true;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_code_sha256 varchar(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_verification_code_sha256 varchar(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_expires_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS activation_token_sha256 varchar(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS activation_expires_at timestamptz;

CREATE INDEX IF NOT EXISTS ix_users_activation_token_sha256 ON users(activation_token_sha256);
