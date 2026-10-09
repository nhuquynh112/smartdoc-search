BEGIN;
CREATE TABLE IF NOT EXISTS corpus_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0)
);
INSERT INTO corpus_state(singleton) VALUES (true) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    file_type text NOT NULL CHECK (file_type IN ('txt', 'pdf')),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    sha256 char(64) NOT NULL UNIQUE,
    word_count integer CHECK (word_count >= 0),
    source_uri text,
    storage_ref text,
    text_ref text,
    raw_text text,
    clean_text text,
    created_at timestamptz NOT NULL DEFAULT now(),
    ingest_status text NOT NULL DEFAULT 'pending'
        CHECK (ingest_status IN ('pending', 'ready', 'failed')),
    error_message text,
    preprocessing_version text,
    preprocessing_config jsonb,
    processed_at timestamptz,
    CHECK (ingest_status <> 'ready' OR
        (storage_ref IS NOT NULL AND text_ref IS NOT NULL AND word_count IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS documents_status_id_idx ON documents(ingest_status, id);
COMMIT;
