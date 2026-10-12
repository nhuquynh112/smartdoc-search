"""Explicit local DB test: creates temporary records and removes them afterwards."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from smartdoc.db import connect
from smartdoc.ingestion import ingest_document, delete_document, load_corpus_snapshot
from tests.database_safety import DisposableDatabaseTestCase

class IngestionIntegrationTests(DisposableDatabaseTestCase):
    def test_ready_duplicate_failed_and_delete(self):
        ids = []
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            # Isolate filesystem writes while using the configured development database.
            from smartdoc.storage_adapter import LocalStorage
            with patch('smartdoc.ingestion.LocalStorage', side_effect=lambda: LocalStorage(base / 'storage')):
                try:
                    with connect() as conn:
                        before = conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()['revision']
                    source = base / 'sample.txt'
                    source.write_text('Kiểm thử cơ sở dữ liệu ' + base.name, encoding='utf-8')
                    ready = ingest_document(source); ids.append(ready['document_id'])
                    self.assertEqual(ready['status'], 'ready')
                    self.assertEqual(ingest_document(source)['status'], 'duplicate')
                    # Query just the new record; snapshot uses the real storage root for existing corpus.
                    with connect() as conn:
                        row = conn.execute('SELECT * FROM documents WHERE id=%s', (ready['document_id'],)).fetchone()
                    self.assertTrue((base/'storage'/row['storage_ref']).is_file())
                    self.assertTrue((base/'storage'/row['text_ref']).read_text())
                    invalid = base / 'invalid.txt'; invalid.write_bytes(b'\xff' + base.name.encode())
                    failed = ingest_document(invalid); ids.append(failed['document_id'])
                    self.assertEqual(failed['status'], 'failed')
                    with connect() as conn:
                        after = conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()['revision']
                    self.assertEqual(after, before + 1)
                    self.assertTrue(delete_document(ready['document_id'])['deleted'])
                    self.assertFalse((base/'storage'/row['storage_ref']).exists())
                finally:
                    for doc_id in ids: delete_document(doc_id)

if __name__ == '__main__': unittest.main()
