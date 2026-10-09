import tempfile
import unittest
import unicodedata
from pathlib import Path
from pypdf import PdfWriter
from smartdoc.document_loader import DocumentLoadError, load_document
from smartdoc.preprocessing import PreprocessingConfig, normalize_text, preprocess_document, preprocess_text

class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def test_utf8_bom_and_uppercase_extension(self):
        p = self.root / 'sample.TXT'
        p.write_text('Cơ sở dữ liệu', encoding='utf-8-sig')
        self.assertEqual(load_document(p), 'Cơ sở dữ liệu')
    def test_invalid_inputs(self):
        for name, data in [('empty.txt', b'  '), ('bad.txt', b'\xff'), ('file.docx', b'x'), ('broken.pdf', b'not a pdf')]:
            p = self.root / name; p.write_bytes(data)
            with self.subTest(name=name), self.assertRaises(DocumentLoadError):
                load_document(p)
    def test_missing(self):
        with self.assertRaises(DocumentLoadError): load_document(self.root / 'missing.txt')
    def test_blank_and_encrypted_pdf(self):
        for encrypted in [False, True]:
            writer = PdfWriter(); writer.add_blank_page(width=200, height=200)
            if encrypted: writer.encrypt('test-password')
            p = self.root / f'{encrypted}.pdf'; writer.write(p)
            with self.subTest(encrypted=encrypted), self.assertRaises(DocumentLoadError): load_document(p)
    def test_text_pdf(self):
        # Minimal valid PDF fixture with a standard-font text stream.
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
        stream = b'BT /F1 12 Tf 10 100 Td (SmartDoc sample) Tj ET'
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
        data = b'%PDF-1.4\n'; offsets = [0]
        for i, obj in enumerate(objects, 1):
            offsets.append(len(data)); data += str(i).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
        xref = len(data); data += b'xref\n0 6\n0000000000 65535 f \n'
        for offset in offsets[1:]: data += f'{offset:010} 00000 n \n'.encode()
        data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
        p = self.root / 'text.pdf'; p.write_bytes(data)
        self.assertIn('SmartDoc sample', load_document(p))

class PreprocessingTests(unittest.TestCase):
    def test_unicode_accents_and_boundaries(self):
        self.assertEqual(normalize_text(unicodedata.normalize('NFD', 'DỮ LIỆU,2026!')), 'dữ liệu 2026')
    def test_sentence_boundaries(self):
        text = "Sinh viên học. Cơ sở dữ liệu quan trọng."
        expected = preprocess_text("Sinh viên học") + " " + preprocess_text("Cơ sở dữ liệu quan trọng")
        self.assertEqual(preprocess_text(text), expected)
    def test_empty(self):
        self.assertEqual(preprocess_text('  !!! '), '')
    def test_whitespace_baseline(self):
        self.assertEqual(preprocess_text('Cơ sở dữ liệu', PreprocessingConfig(segment_words=False)), 'cơ sở dữ liệu')
    def test_vietnamese_segmentation(self):
        r = preprocess_document('Sinh viên học công nghệ thông tin.')
        self.assertIn('sinh_viên', r.tokens)
        self.assertEqual(r.word_count, len(r.tokens))
        self.assertEqual(r.clean_text, preprocess_text('Sinh viên học công nghệ thông tin.'))
    def test_stopwords_and_count(self):
        c = PreprocessingConfig(segment_words=False, remove_stopwords=True, stopwords=frozenset({'và'}))
        r = preprocess_document('học và làm', c)
        self.assertEqual(r.clean_text, 'học làm'); self.assertEqual(r.word_count, 3)
        with self.assertRaises(ValueError): preprocess_text('test', PreprocessingConfig(remove_stopwords=True))

if __name__ == '__main__': unittest.main()
