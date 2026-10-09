"""Serialized ingestion and data-service contracts for the initial demo."""
from pathlib import Path
from .db import connect
from .metadata_extractor import extract_metadata
from .document_loader import load_document_bytes, DocumentLoadError
from .preprocessing import preprocess_document
from .storage_adapter import LocalStorage

# Also used by snapshot reads/deletion. TV2 should read snapshot under this lock.
CORPUS_LOCK = 73426001

def ingest_document(path, source_uri=None):
    path = Path(path)
    if path.suffix.lower() not in {'.txt', '.pdf'}:
        raise DocumentLoadError('Only TXT and PDF documents are supported.')
    payload = path.read_bytes()
    meta = extract_metadata(path, source_uri, payload=payload)
    storage = LocalStorage()
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (CORPUS_LOCK,))
        existing = conn.execute('SELECT id, ingest_status FROM documents WHERE sha256=%s', (meta['sha256'],)).fetchone()
        if existing:
            return {'document_id': existing['id'], 'status': 'duplicate', 'existing_status': existing['ingest_status']}
        doc = conn.execute('''INSERT INTO documents(title,file_type,size_bytes,sha256,source_uri)
            VALUES (%(title)s,%(file_type)s,%(size_bytes)s,%(sha256)s,%(source_uri)s) RETURNING id''', meta).fetchone()
        doc_id = doc['id']
        original_ref = f"originals/{doc_id}.{meta['file_type']}"
        text_ref = f'processed/{doc_id}.txt'
        try:
            processed = preprocess_document(load_document_bytes(payload, path.suffix))
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
        conn.execute("""UPDATE documents SET ingest_status='ready',word_count=%s,storage_ref=%s,text_ref=%s
                        WHERE id=%s""", (processed.word_count, original_ref, text_ref, doc_id))
        conn.execute('UPDATE corpus_state SET revision=revision+1 WHERE singleton')
        return {'document_id': doc_id, 'status': 'ready', 'word_count': processed.word_count}

def load_corpus_snapshot():
    storage = LocalStorage()
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (CORPUS_LOCK,))
        revision = conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()['revision']
        rows = conn.execute("SELECT id AS document_id,title,source_uri,storage_ref,text_ref FROM documents WHERE ingest_status='ready' ORDER BY id").fetchall()
        for row in rows:
            row['clean_text'] = storage.read_text(row.pop('text_ref'))
    return {'corpus_revision': revision, 'documents': rows}

def load_documents_for_index():
    return load_corpus_snapshot()['documents']

def get_documents_by_ids(ids):
    if not ids: return []
    with connect() as conn:
        rows = conn.execute("SELECT id AS document_id,title,source_uri,storage_ref,word_count FROM documents WHERE id=ANY(%s) AND ingest_status='ready'", (list(ids),)).fetchall()
    by_id = {r['document_id']: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]

def get_document_text(document_id):
    with connect() as conn:
        row = conn.execute("SELECT text_ref FROM documents WHERE id=%s AND ingest_status='ready'", (document_id,)).fetchone()
    if not row: raise LookupError('Ready document not found.')
    return LocalStorage().read_text(row['text_ref'])

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
