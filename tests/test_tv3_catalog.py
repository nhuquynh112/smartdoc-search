"""Standalone tests for TV3 filters; no DB and no external packages needed."""
import unittest
from app.catalog_utils import fold, category_label, categories, filter_catalog, page_slice

SAMPLE = [
    {"document_id": 5, "title": "Xe Điện Việt Nam", "category": "Công nghệ", "word_count": 100, "clean_text": "nang luong sach"},
    {"document_id": 8, "title": "Bóng đá Việt Nam", "category": "Thể thao", "word_count": 230, "clean_text": "the thao"},
    {"document_id": 12, "title": "Ô tô điện", "category": "Công nghệ", "word_count": 180, "clean_text": "giao thong xanh"},
]

class CatalogTests(unittest.TestCase):
    def test_case_diacritics(self):
        self.assertEqual(fold("Điện Việt Nam"), "dien viet nam")
        # Vietnamese 'đ' needs a custom normalization to match ASCII 'd'.
        self.assertEqual(len(filter_catalog(SAMPLE, "dien")), 2)
        self.assertEqual(len(filter_catalog(SAMPLE, "điện")), 2)

    def test_categories(self):
        self.assertEqual(categories(SAMPLE)["Công nghệ"], 2)
        self.assertEqual(category_label({}), "Chưa phân loại")

    def test_filter_sort(self):
        self.assertEqual([d["document_id"] for d in filter_catalog(SAMPLE, category="Công nghệ")], [12, 5])
        self.assertEqual(filter_catalog(SAMPLE, "nang luong", search_in="Tiêu đề & nội dung đã xử lý")[0]["document_id"], 5)
        self.assertEqual(filter_catalog(SAMPLE, sort_by="Nhiều từ nhất")[0]["document_id"], 8)

    def test_pagination(self):
        rows, page, total = page_slice(SAMPLE, 100, 2)
        self.assertEqual((page, total, len(rows)), (2, 2, 1))
        self.assertEqual(page_slice([], 0, 5), ([], 1, 1))

    def test_vietnamese_compound_tokens(self):
        docs = [{"document_id": 1, "title": "Bài viết", "clean_text": "năng_lượng sạch"}]
        for query in ("nang luong", "năng_lượng"):
            self.assertEqual(len(filter_catalog(docs, query, search_in="Tiêu đề & nội dung đã xử lý")), 1)

if __name__ == "__main__":
    unittest.main()
