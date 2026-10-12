"""Persistent bookmarks shared by the local workspace (no user accounts)."""
from .db import connect


def load_saved_document_ids():
    with connect() as conn:
        rows = conn.execute("""SELECT s.document_id FROM saved_documents s
            JOIN documents d ON d.id=s.document_id
            WHERE d.ingest_status='ready' ORDER BY s.document_id""").fetchall()
    return [row['document_id'] for row in rows]


def set_document_saved(document_id: int, is_saved: bool):
    if type(document_id) is not int or document_id <= 0 or type(is_saved) is not bool:
        raise ValueError('Invalid bookmark input.')
    with connect() as conn:
        if is_saved:
            row = conn.execute("SELECT id FROM documents WHERE id=%s AND ingest_status='ready' FOR KEY SHARE",
                               (document_id,)).fetchone()
            if not row:
                raise LookupError('Tài liệu không còn sẵn sàng để lưu.')
            conn.execute('INSERT INTO saved_documents(document_id) VALUES (%s) ON CONFLICT DO NOTHING',
                         (document_id,))
        else:
            conn.execute('DELETE FROM saved_documents WHERE document_id=%s', (document_id,))
