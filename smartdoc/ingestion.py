"""Serialized ingestion and data-service contracts for the initial demo."""
from pathlib import Path
from .db import connect
from .metadata_extractor import extract_metadata
from .document_loader import load_document_bytes, DocumentLoadError
from .preprocessing import preprocess_document, pipeline_manifest
from psycopg.types.json import Jsonb
from .storage_adapter import LocalStorage

# Also used by snapshot reads/deletion. TV2 should read snapshot under this lock.
CORPUS_LOCK = 73426001

def ingest_document(path, source_uri=None, *, title=None, corpus_name="integration", category=None, dataset_id=None, retry_failed=False):
    path = Path(path)
    if path.suffix.lower() not in {'.txt', '.pdf'}:
        raise DocumentLoadError('Only TXT and PDF documents are supported.')
    payload = path.read_bytes()
    meta = extract_metadata(path, source_uri, payload=payload)
    if title is not None:
        if not title.strip(): raise ValueError('Title must not be empty.')
        meta['title'] = title.strip()
    meta.update(corpus_name=corpus_name, category=category, dataset_id=dataset_id)
    storage = LocalStorage()
    manifest = pipeline_manifest()
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (CORPUS_LOCK,))
        existing = conn.execute('SELECT id, ingest_status FROM documents WHERE sha256=%s', (meta['sha256'],)).fetchone()
        if existing:
            if existing['ingest_status'] != 'failed' or not retry_failed:
                return {'document_id': existing['id'], 'status': 'duplicate', 'existing_status': existing['ingest_status']}
            doc_id = existing['id']
            conn.execute("UPDATE documents SET ingest_status='pending',error_message=NULL WHERE id=%s", (doc_id,))
        else:
            doc = conn.execute('''INSERT INTO documents(title,file_type,size_bytes,sha256,source_uri,corpus_name,category,dataset_id)
                VALUES (%(title)s,%(file_type)s,%(size_bytes)s,%(sha256)s,%(source_uri)s,%(corpus_name)s,%(category)s,%(dataset_id)s) RETURNING id''', meta).fetchone()
            doc_id = doc['id']
        original_ref = f"originals/{doc_id}.{meta['file_type']}"
        text_ref = f'processed/{doc_id}.txt'
        try:
            raw_text = load_document_bytes(payload, path.suffix)
            processed = preprocess_document(raw_text)
            if not processed.clean_text:
                raise DocumentLoadError('No searchable tokens remain after preprocessing.')
            storage.write(original_ref, payload)
            storage.write(text_ref, processed.clean_text.encode('utf-8'))
        except (DocumentLoadError, OSError, ValueError) as exc:
            cleanup_errors = []
            for ref in (original_ref, text_ref):
                try: storage.delete(ref)
                except OSError: cleanup_errors.append(ref)
            error = str(exc)
            if cleanup_errors: error += '; cleanup required: ' + ', '.join(cleanup_errors)
            conn.execute("UPDATE documents SET ingest_status='failed',error_message=%s WHERE id=%s", (error, doc_id))
            return {'document_id': doc_id, 'status': 'failed', 'error': error}
        # A failed upload can be retried with a corrected extension. Persist the
        # successful loader's type together with its storage reference.
        conn.execute("""UPDATE documents SET ingest_status='ready',file_type=%s,word_count=%s,storage_ref=%s,text_ref=%s, preprocessing_version=%s, preprocessing_config=%s, processed_at=now(),error_message=NULL,raw_text=%s,clean_text=%s
                        WHERE id=%s""", (meta['file_type'], processed.word_count, original_ref, text_ref, manifest['fingerprint'], Jsonb(manifest['settings']), raw_text, processed.clean_text, doc_id))
        conn.execute('UPDATE corpus_state SET revision=revision+1 WHERE singleton')
        return {'document_id': doc_id, 'status': 'ready', 'word_count': processed.word_count}

def load_corpus_snapshot(corpus_name=None):
    storage = LocalStorage()
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (CORPUS_LOCK,))
        revision = conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()['revision']
        rows = conn.execute("SELECT id AS document_id,title,source_uri,storage_ref,clean_text,preprocessing_version,preprocessing_config,corpus_name,category,dataset_id FROM documents WHERE ingest_status='ready' AND (%s::text IS NULL OR corpus_name=%s) ORDER BY id", (corpus_name, corpus_name)).fetchall()
        manifest = pipeline_manifest()
        if any(r['preprocessing_version'] != manifest['fingerprint'] or r['preprocessing_config'] != manifest['settings'] for r in rows):
            raise ValueError('Corpus preprocessing is unknown or outdated. Run python -m scripts.reprocess_corpus.')
        if any(not r['clean_text'] for r in rows):
            raise ValueError('Missing DB text. Run python -m scripts.backfill_document_text.')
    return {'corpus_revision': revision, 'corpus_name': corpus_name, 'preprocessing': manifest, 'documents': rows}

def load_documents_for_index():
    return load_corpus_snapshot()['documents']

def load_corpus_revision():
    """Cheap uncached freshness check; a single statement sees one DB snapshot."""
    with connect() as conn:
        return conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()['revision']

def get_documents_by_ids(ids):
    if not ids: return []
    with connect() as conn:
        rows = conn.execute("SELECT id AS document_id,title,source_uri,storage_ref,word_count,category,corpus_name,clean_text FROM documents WHERE id=ANY(%s) AND ingest_status='ready'", (list(ids),)).fetchall()
    by_id = {r['document_id']: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]

def get_document_text(document_id):
    with connect() as conn:
        row = conn.execute("SELECT raw_text FROM documents WHERE id=%s AND ingest_status='ready'", (document_id,)).fetchone()
    if not row: raise LookupError('Ready document not found.')
    return row['raw_text']

def delete_document(document_id):
    # Commit corpus removal before filesystem cleanup, so stale references cannot be indexed.
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (CORPUS_LOCK,))
        row = conn.execute('DELETE FROM documents WHERE id=%s RETURNING ingest_status,storage_ref,text_ref', (document_id,)).fetchone()
        if not row: return {'deleted': False, 'cleanup_errors': []}
        if row['ingest_status'] == 'ready':
            conn.execute('UPDATE corpus_state SET revision=revision+1 WHERE singleton')
    errors = []
    for ref in (row['storage_ref'], row['text_ref']):
        if ref:
            try: LocalStorage().delete(ref)
            except OSError: errors.append(ref)
    return {'deleted': True, 'cleanup_errors': errors}
