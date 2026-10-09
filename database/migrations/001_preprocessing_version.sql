ALTER TABLE documents ADD COLUMN IF NOT EXISTS preprocessing_version text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS preprocessing_config jsonb;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS processed_at timestamptz;
