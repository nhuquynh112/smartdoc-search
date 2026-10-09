"""Reprocess ready records as one database transaction using new immutable files."""
import hashlib
from uuid import uuid4
from psycopg.types.json import Jsonb
from .db import connect
from .ingestion import CORPUS_LOCK
from .document_loader import load_document_bytes, DocumentLoadError
from .preprocessing import pipeline_manifest, preprocess_document
from .storage_adapter import LocalStorage


def reprocess_corpus():
    storage = LocalStorage()
    manifest = pipeline_manifest()
    try:
        with connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(%s)', (CORPUS_LOCK,))
            rows = conn.execute("SELECT * FROM documents WHERE ingest_status='ready' ORDER BY id").fetchall()
            updates = []
            for row in rows:
                if row['preprocessing_version'] == manifest['fingerprint'] and row['preprocessing_config'] == manifest['settings']:
                    continue
                payload = storage.resolve(row['storage_ref']).read_bytes()
                if hashlib.sha256(payload).hexdigest() != row['sha256']:
                    raise ValueError(f"Original hash mismatch for document {row['id']}")
                raw_text = load_document_bytes(payload, '.'+row['file_type'])
                result = preprocess_document(raw_text)
                if not result.clean_text: raise DocumentLoadError(f"No tokens for document {row['id']}")
                ref = f"processed/{row['id']}-{uuid4().hex}.txt"
                storage.write(ref, result.clean_text.encode('utf-8'))
                updates.append((result.word_count, ref, manifest['fingerprint'], Jsonb(manifest['settings']), raw_text, result.clean_text, row['id']))
            for values in updates:
                conn.execute('''UPDATE documents SET word_count=%s,text_ref=%s,preprocessing_version=%s,
                             preprocessing_config=%s,processed_at=now(),raw_text=%s,clean_text=%s WHERE id=%s''', values)
            if updates: conn.execute('UPDATE corpus_state SET revision=revision+1 WHERE singleton')
            revision = conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()['revision']
    except Exception:
        # Retain new files on ambiguous commit failure; never delete a potentially committed reference.
        # They can be reconciled later. Old files and original files are never modified.
        raise
    return {'updated_documents':len(updates), 'corpus_revision':revision,
            'preprocessing':manifest, 'retained_old_files':True}
