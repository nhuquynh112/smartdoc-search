ALTER TABLE documents ADD COLUMN IF NOT EXISTS raw_text text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS clean_text text;
-- Legacy records are backfilled before validation. New ready records must have text.
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='documents_ready_text_check' AND conrelid='documents'::regclass) THEN
ALTER TABLE documents ADD CONSTRAINT documents_ready_text_check CHECK (
    ingest_status <> 'ready' OR
    (raw_text IS NOT NULL AND length(btrim(raw_text)) > 0 AND
     clean_text IS NOT NULL AND length(btrim(clean_text)) > 0)
) NOT VALID;
END IF;
END $$;
