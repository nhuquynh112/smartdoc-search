"""Move legacy extracted/processed text into PostgreSQL without changing IDs."""
import hashlib
from smartdoc.db import connect
from smartdoc.ingestion import CORPUS_LOCK
from smartdoc.storage_adapter import LocalStorage
from smartdoc.document_loader import load_document_bytes


def main():
    storage = LocalStorage()
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (CORPUS_LOCK,))
        rows = conn.execute("SELECT * FROM documents WHERE ingest_status='ready' AND (raw_text IS NULL OR clean_text IS NULL) ORDER BY id").fetchall()
        for row in rows:
            payload = storage.resolve(row['storage_ref']).read_bytes()
            if hashlib.sha256(payload).hexdigest() != row['sha256']:
                raise ValueError(f"Original hash mismatch: {row['id']}")
            raw = load_document_bytes(payload, '.'+row['file_type'])
            clean = storage.read_text(row['text_ref'])
            if not clean.strip(): raise ValueError(f"Empty processed text: {row['id']}")
            conn.execute('UPDATE documents SET raw_text=%s,clean_text=%s WHERE id=%s', (raw,clean,row['id']))
        conn.execute('ALTER TABLE documents VALIDATE CONSTRAINT documents_ready_text_check')
    print(f'Backfilled {len(rows)} documents; IDs, processed content and corpus revision unchanged.')

if __name__=='__main__': main()
