from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import smartdoc.document_loader as loader


def test_byte_limit_rejects_before_pdf_parsing(monkeypatch):
    monkeypatch.setattr(loader, 'MAX_DOCUMENT_BYTES', 3)
    parser = Mock(side_effect=AssertionError('Parser must not run'))
    monkeypatch.setattr(loader, 'PdfReader', parser)
    with pytest.raises(loader.DocumentLoadError, match='8 MB'):
        loader.load_document_bytes(b'four', '.pdf')
    parser.assert_not_called()


def test_pdf_page_limit_rejects_before_extraction(monkeypatch):
    page = Mock()
    monkeypatch.setattr(loader, 'MAX_PDF_PAGES', 1)
    monkeypatch.setattr(loader, 'PdfReader', lambda _: SimpleNamespace(is_encrypted=False, pages=[page, page]))
    with pytest.raises(loader.DocumentLoadError, match='page'):
        loader.load_document_bytes(b'pdf', '.pdf')
    page.extract_text.assert_not_called()


def test_pdf_text_limit_stops_before_remaining_pages(monkeypatch):
    pages = [Mock(), Mock(), Mock()]
    for page in pages:
        page.extract_text.return_value = 'abc'
    monkeypatch.setattr(loader, 'MAX_EXTRACTED_CHARACTERS', 5)
    monkeypatch.setattr(loader, 'PdfReader', lambda _: SimpleNamespace(is_encrypted=False, pages=pages))
    with pytest.raises(loader.DocumentLoadError, match='text exceeds'):
        loader.load_document_bytes(b'pdf', '.pdf')
    pages[2].extract_text.assert_not_called()


def test_txt_output_limit_and_boundary(monkeypatch):
    monkeypatch.setattr(loader, 'MAX_EXTRACTED_CHARACTERS', 3)
    assert loader.load_document_bytes(b'abc', '.txt') == 'abc'
    with pytest.raises(loader.DocumentLoadError, match='text exceeds'):
        loader.load_document_bytes(b'abcd', '.txt')
