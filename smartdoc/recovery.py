"""Reconcile managed storage references while holding the corpus mutation lock."""
from datetime import datetime, timezone
from uuid import uuid4
from .db import connect
from .ingestion import CORPUS_LOCK
from .storage_adapter import LocalStorage


def reconcile_storage(quarantine=False, storage=None):
    storage = storage or LocalStorage()
    result = {'missing_references': [], 'orphan_files': [], 'quarantined': [], 'pending_document_ids': [], 'errors': []}
    # Referenced paths include all records, not just ready: never move a referenced file.
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (CORPUS_LOCK,))
        rows = conn.execute('SELECT id,storage_ref,text_ref,ingest_status FROM documents ORDER BY id').fetchall()
        referenced = set()
        for row in rows:
            if row['ingest_status'] == 'pending': result['pending_document_ids'].append(row['id'])
            for key in ['storage_ref','text_ref']:
                if row[key]:
                    try:
                        path = storage.resolve(row[key]); referenced.add(path)
                        if not path.is_file(): result['missing_references'].append({'document_id':row['id'],'field':key,'reference':row[key]})
                    except ValueError:
                        result['errors'].append({'document_id':row['id'],'reference':row[key],'error':'unsafe reference'})
        run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
        for directory in ['originals','processed']:
            folder = storage.root / directory
            if not folder.exists(): continue
            for path in sorted(folder.rglob('*')):
                if not path.is_file() or path.name == '.gitkeep': continue
                if path.is_symlink():
                    result['errors'].append({'reference':str(path.relative_to(storage.root)),'error':'symlink skipped'}); continue
                if path.resolve() in referenced: continue
                reference = str(path.relative_to(storage.root))
                result['orphan_files'].append(reference)
                if quarantine:
                    target = storage.root/'quarantine'/run/path.relative_to(storage.root)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    try:
                        path.rename(target)
                        result['quarantined'].append(str(target.relative_to(storage.root)))
                    except OSError as exc: result['errors'].append({'reference':reference,'error':type(exc).__name__})
    return result
