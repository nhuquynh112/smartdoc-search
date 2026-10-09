import unittest
from scripts.export_corpus import validate_snapshot

class ExportContractTests(unittest.TestCase):
    def row(self, i):
        return dict(document_id=i,title='test',clean_text='dữ_liệu',source_uri=None,storage_ref='originals/test.txt')
    def test_nonconsecutive_ids(self):
        validate_snapshot({'documents':[self.row(1),self.row(7)]})
    def test_invalid_order_duplicate_and_empty(self):
        for rows in [[self.row(2),self.row(1)], [self.row(1),self.row(1)], [{**self.row(1),'clean_text':''}]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError): validate_snapshot({'documents':rows})

if __name__ == '__main__': unittest.main()
