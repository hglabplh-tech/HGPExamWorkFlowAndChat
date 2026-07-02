-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
-- Store normalized JSON thesauri used by application-level full-text expansion.

CREATE TABLE IF NOT EXISTS thesauri (
    id uuid PRIMARY KEY,
    name varchar(120) NOT NULL,
    language varchar(20) NOT NULL DEFAULT 'simple',
    source_format varchar(40) NOT NULL DEFAULT 'solr_synonyms',
    entries jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_sha256 varchar(64) NOT NULL UNIQUE,
    active boolean NOT NULL DEFAULT true,
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_thesauri_name_language UNIQUE (name, language)
);

CREATE INDEX IF NOT EXISTS ix_thesauri_name ON thesauri(name);
CREATE INDEX IF NOT EXISTS ix_thesauri_language ON thesauri(language);
CREATE INDEX IF NOT EXISTS ix_thesauri_active ON thesauri(active);
CREATE INDEX IF NOT EXISTS ix_thesauri_source_sha256 ON thesauri(source_sha256);
