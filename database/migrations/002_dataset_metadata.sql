ALTER TABLE documents ADD COLUMN IF NOT EXISTS corpus_name text NOT NULL DEFAULT 'integration';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS category text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS dataset_id text;
CREATE INDEX IF NOT EXISTS documents_corpus_idx ON documents(corpus_name, ingest_status, id);
