-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
CREATE TABLE IF NOT EXISTS mail_server_settings (
  id uuid PRIMARY KEY,
  name varchar(120) UNIQUE NOT NULL DEFAULT 'default',
  smtp_host varchar(255),
  smtp_port integer NOT NULL DEFAULT 587,
  smtp_username varchar(255),
  smtp_password varchar(1024),
  smtp_starttls boolean NOT NULL DEFAULT true,
  smtp_ssl boolean NOT NULL DEFAULT false,
  email_from varchar(320),
  support_email varchar(320),
  imap_host varchar(255),
  imap_port integer NOT NULL DEFAULT 993,
  imap_username varchar(255),
  imap_password varchar(1024),
  imap_ssl boolean NOT NULL DEFAULT true,
  active boolean NOT NULL DEFAULT true,
  updated_by uuid REFERENCES users(id),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mail_server_settings_name ON mail_server_settings(name);
