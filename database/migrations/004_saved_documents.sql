CREATE TABLE IF NOT EXISTS saved_documents (
    document_id bigint PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    saved_at timestamptz NOT NULL DEFAULT now()
);
