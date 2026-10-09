import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from smartdoc.data_quality import inspect_document, summarize
from smartdoc.storage_adapter import LocalStorage

class DataQualityTests(unittest.TestCase):
    def test_valid_missing_and_tampered_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = LocalStorage(Path(folder))
            storage.write('originals/1.txt', b'example')
            storage.write('processed/1.txt', 'dữ_liệu tốt'.encode())
            row = dict(id=1, ingest_status='ready', file_type='txt', source_uri=None,
                       storage_ref='originals/1.txt', text_ref='processed/1.txt',
                       size_bytes=7, sha256=sha256(b'example').hexdigest(), word_count=2)
            good = inspect_document(row, storage)
            self.assertEqual(good['storage_check'], 'passed')
            self.assertEqual(good['source_status'], 'missing')
            storage.write('originals/1.txt', b'changed')
            self.assertIn('hash_mismatch', inspect_document(row, storage)['quality_issues'])
            storage.delete('processed/1.txt')
            self.assertEqual(inspect_document(row, storage)['storage_check'], 'issues')
    def test_empty_and_failed_summary(self):
        self.assertEqual(summarize([], 0)['mean_word_count_before_stopwords'], 0)
        with tempfile.TemporaryDirectory() as folder:
            row = inspect_document(dict(ingest_status='failed', source_uri='file:///tmp/a'), LocalStorage(folder))
            self.assertEqual(row['storage_check'], 'not_checked')
            self.assertEqual(row['source_status'], 'non_web')
            self.assertEqual(summarize([row], 3)['status_counts'], {'failed': 1})

if __name__ == '__main__': unittest.main()
