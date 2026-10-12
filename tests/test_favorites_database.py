"""Bookmarks persist across connections without modifying retrieval inputs."""
import pytest

from smartdoc.db import connect
from smartdoc.favorites import load_saved_document_ids, set_document_saved
from smartdoc.ingestion import delete_document, ingest_document
from tests.database_safety import require_disposable_database


@pytest.fixture(autouse=True)
def isolated_database():
    require_disposable_database()


@pytest.fixture
def document(tmp_path):
    path = tmp_path / 'favorite.txt'
    path.write_text('Tài liệu kiểm thử lưu và đọc lại ' + str(tmp_path), encoding='utf-8')
    result = ingest_document(path)
    assert result['status'] == 'ready'
    yield result['document_id']
    delete_document(result['document_id'])


def test_persists_and_removes_idempotently_without_changing_revision(document):
    with connect() as conn:
        revision = conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()['revision']
    set_document_saved(document, True)
    set_document_saved(document, True)
    # Each service call opens a fresh connection, as after a browser/server restart.
    assert document in load_saved_document_ids()
    with connect() as conn:
        assert conn.execute('SELECT count(*) AS n FROM saved_documents WHERE document_id=%s',
                            (document,)).fetchone()['n'] == 1
    set_document_saved(document, False)
    set_document_saved(document, False)
    assert document not in load_saved_document_ids()
    with connect() as conn:
        assert conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()['revision'] == revision


def test_deleted_document_cascades_bookmark(document):
    set_document_saved(document, True)
    delete_document(document)
    assert document not in load_saved_document_ids()
    with connect() as conn:
        assert conn.execute('SELECT document_id FROM saved_documents WHERE document_id=%s',
                            (document,)).fetchone() is None
    with pytest.raises(LookupError):
        set_document_saved(document, True)


def test_failed_document_cannot_be_saved(tmp_path):
    path = tmp_path / 'empty.txt'
    path.write_bytes(b'')
    result = ingest_document(path)
    assert result['status'] == 'failed'
    try:
        with pytest.raises(LookupError):
            set_document_saved(result['document_id'], True)
    finally:
        delete_document(result['document_id'])
