"""Real TXT/PDF upload tests; enabled only by the disposable-database runner."""
import io
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.upload_service import process_uploads
from smartdoc.ingestion import get_document_text, ingest_document
from tests.database_safety import require_disposable_database as check_disposable_database


@pytest.fixture(autouse=True)
def require_disposable_database():
    check_disposable_database()


def pdf_payload(text=None):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    if text:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def file(name, payload):
    return SimpleNamespace(name=name, size=len(payload), getvalue=lambda: payload)


def test_real_upload_txt_pdf_duplicate_and_reader():
    files = [file("sample.txt", "Kiểm thử nhập tài liệu và giao thông xanh".encode()),
             file("sample.pdf", pdf_payload("Tai lieu PDF co van ban ve cong nghe"))]
    results = process_uploads(files, "Integration", ingest_fn=ingest_document)
    assert [row[1] for row in results] == ["ready", "ready"]
    assert [row[1] for row in process_uploads(files, "Integration", ingest_fn=ingest_document)] == ["duplicate", "duplicate"]
    from smartdoc.ingestion import load_corpus_snapshot
    docs = load_corpus_snapshot("user_uploads")["documents"]
    assert len(docs) == 2
    assert all(get_document_text(doc["document_id"]).strip() for doc in docs)


def test_blank_pdf_corrupt_pdf_and_empty_txt_are_failed():
    files = [file("scan.pdf", pdf_payload()), file("broken.pdf", b"not a PDF"), file("empty.txt", b"")]
    results = process_uploads(files, "Integration", ingest_fn=ingest_document)
    assert [row[1] for row in results] == ["failed", "failed", "failed"]
