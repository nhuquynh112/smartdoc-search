import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from smartdoc.db import connect
from smartdoc.ingestion import ingest_document,delete_document
from smartdoc.storage_adapter import LocalStorage
from smartdoc.recovery import reconcile_storage
from tests.database_safety import DisposableDatabaseTestCase

class RecoveryTests(DisposableDatabaseTestCase):
    def test_storage_failure_retry_keeps_id(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'sample.txt'
            source.write_text('Kiểm thử phục hồi dữ liệu '+root.name,encoding='utf-8')
            storage=LocalStorage(root/'storage'); ids=[]
            with patch('smartdoc.ingestion.LocalStorage',return_value=storage):
                try:
                    original_write=storage.write
                    def fail_text(ref,payload):
                        if ref.startswith('processed/'): raise OSError('Simulated disk failure')
                        original_write(ref,payload)
                    with patch.object(storage,'write',side_effect=fail_text):
                        failed=ingest_document(source)
                    ids.append(failed['document_id'])
                    self.assertEqual(failed['status'],'failed')
                    self.assertFalse(list((storage.root/'originals').glob('*.txt')))
                    retried=ingest_document(source,retry_failed=True)
                    self.assertEqual(retried['document_id'],failed['document_id'])
                    self.assertEqual(retried['status'],'ready')
                    with connect() as c:
                        row=c.execute('SELECT error_message,raw_text,clean_text FROM documents WHERE id=%s',(retried['document_id'],)).fetchone()
                    self.assertIsNone(row['error_message']);self.assertTrue(row['raw_text'] and row['clean_text'])
                finally:
                    for i in ids:delete_document(i)
    def test_quarantine_preserves_files(self):
        with tempfile.TemporaryDirectory() as folder:
            storage=LocalStorage(folder)
            storage.write('originals/unreferenced.txt',b'temporary fixture')
            report=reconcile_storage(storage=storage)
            self.assertIn('originals/unreferenced.txt',
                          [Path(ref).as_posix() for ref in report['orphan_files']])
            self.assertTrue(storage.resolve('originals/unreferenced.txt').exists())
            report=reconcile_storage(quarantine=True,storage=storage)
            self.assertEqual(len(report['quarantined']),1)
            self.assertEqual(storage.resolve(report['quarantined'][0]).read_bytes(),b'temporary fixture')

if __name__=='__main__':unittest.main()
