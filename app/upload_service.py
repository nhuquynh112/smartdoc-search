"""Validate uploaded files before calling the shared ingestion API."""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import tempfile


MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def process_uploads(files, category, *, ingest_fn, mutation_lock=None):
    """Return per-file feedback; one bad upload must not stop the batch."""
    feedback = []
    with mutation_lock if mutation_lock is not None else nullcontext():
        for uploaded in files:
            name = Path(str(uploaded.name).replace("\\", "/")).name
            suffix = Path(name).suffix.lower()
            if suffix not in {".txt", ".pdf"}:
                feedback.append((name, "error", "Định dạng không được hỗ trợ."))
                continue
            try:
                # Check actual bytes as well as browser-provided size.
                if uploaded.size > MAX_UPLOAD_BYTES:
                    feedback.append((name, "error", "Tệp vượt quá giới hạn 8 MB."))
                    continue
                payload = uploaded.getvalue()
                if len(payload) > MAX_UPLOAD_BYTES:
                    feedback.append((name, "error", "Tệp vượt quá giới hạn 8 MB."))
                    continue
                with tempfile.TemporaryDirectory(prefix="smartdoc_upload_") as directory:
                    # A fixed local name also handles Windows reserved filenames safely.
                    local_path = Path(directory) / f"upload{suffix}"
                    local_path.write_bytes(payload)
                    result = ingest_fn(local_path, title=Path(name).stem,
                                       corpus_name="user_uploads", category=category.strip() or None,
                                       retry_failed=True)
                status = str(result.get("status", "failed"))
                if status == "ready":
                    detail = f"Đã lưu #{result.get('document_id')} · {result.get('word_count', 0)} từ"
                elif status == "duplicate":
                    existing_status = result.get("existing_status", "ready")
                    if existing_status == "ready":
                        detail = "Tệp đã có trong thư viện."
                    else:
                        status = "failed"
                        detail = "Tệp đã được ghi nhận nhưng chưa sẵn sàng; kiểm tra lỗi nhập rồi thử lại."
                else:
                    detail = str(result.get("error") or "Không thể xử lý tệp.")
                feedback.append((name, status, detail))
            except Exception as exc:
                feedback.append((name, "error", str(exc)))
    return feedback
