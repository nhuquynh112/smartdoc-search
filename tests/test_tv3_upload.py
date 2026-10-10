"""Upload boundary tests with an isolated ingestion stub; no database writes."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.upload_service import MAX_UPLOAD_BYTES, process_uploads


def upload(name, data=b"hello", size=None):
    return SimpleNamespace(name=name, size=len(data) if size is None else size, getvalue=lambda: data)


def test_unsupported_and_oversized_files_never_reach_ingestion():
    ingest = Mock()
    files = [upload("a.exe"), upload("a.txt", size=MAX_UPLOAD_BYTES + 1),
             upload("b.pdf", b"x" * (MAX_UPLOAD_BYTES + 1), size=1)]
    assert all(row[1] == "error" for row in process_uploads(files, "", ingest_fn=ingest))
    ingest.assert_not_called()


def test_path_traversal_reserved_filename_and_temp_cleanup():
    paths = []
    def ingest(path, **kwargs):
        paths.append(path)
        assert Path(path).name == "upload.txt"
        assert Path(path).read_bytes() == b"hello"
        assert kwargs == {"title": "CON", "corpus_name": "user_uploads", "category": None, "retry_failed": True}
        return {"status": "ready", "document_id": 5, "word_count": 1}
    result = process_uploads([upload(r"..\..\CON.txt")], "  ", ingest_fn=ingest)
    assert result[0][0:2] == ("CON.txt", "ready")
    assert all(not path.exists() for path in paths)


def test_failed_duplicate_and_exception_do_not_stop_batch():
    ingest = Mock(side_effect=[ValueError("bad PDF"), {"status": "duplicate"},
                               {"status": "failed", "error": "No searchable text"},
                               {"status": "ready", "document_id": 9, "word_count": 4}])
    result = process_uploads([upload(f"{i}.txt") for i in range(4)], "Test", ingest_fn=ingest)
    assert [row[1] for row in result] == ["error", "duplicate", "failed", "ready"]
    assert ingest.call_count == 4
    assert all(not call.args[0].exists() for call in ingest.call_args_list)


def test_duplicate_of_non_ready_file_is_not_reported_as_imported():
    ingest = Mock(return_value={"status": "duplicate", "existing_status": "failed"})
    result = process_uploads([upload("a.txt")], "", ingest_fn=ingest)
    assert result[0][1] == "failed"
    assert ingest.call_args.kwargs["retry_failed"] is True
