"""Human review of a frozen evaluation kit; never infer relevance from scores.

Only the evaluation CSV/JSON files are writable. The live corpus is read through
the existing data API. Atomic file replacement, a short cross-process lock and
an optimistic token protect two review sessions from overwriting each other.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from evaluation import (
    EvaluationInputError, JUDGMENT_FIELDS, QUERY_FIELDS, canonical_sha256,
    query_semantic_sha256, validate_evaluation_inputs, validate_frozen_corpus,
)


class ReviewConflictError(EvaluationInputError):
    """A different session/editor changed the kit after this form was loaded."""


_WRITE_LOCK = RLock()
_FILES = ("corpus_manifest.json", "protocol.json", "evaluation_queries.csv", "relevance_judgments.csv")


def _snapshot_loader(corpus_name):
    from smartdoc.ingestion import load_corpus_snapshot
    return load_corpus_snapshot(corpus_name)


def _text_loader(document_id):
    from smartdoc.ingestion import get_document_text
    return get_document_text(document_id)


def _coverage_checker(snapshot, queries):
    # This internal call selects IDs only. No score or ranking is sent to UI.
    from scripts.prepare_evaluation import top20_pool
    return top20_pool(snapshot, queries)


def _human(value, field):
    if not isinstance(value, str) or not value.strip():
        raise EvaluationInputError(f"Cần ghi tên người thật ở trường {field}.")
    value = value.strip()
    if value.casefold() in {"ai", "chatgpt", "codex", "auto", "automatic", "todo", "unknown"}:
        raise EvaluationInputError(f"{field} phải là tên người rà soát thực tế.")
    return value


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def _atomic_write(path, payload):
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _exclusive_write(directory):
    with _WRITE_LOCK:
        lock_path = directory / ".evaluation_review.lock"
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ReviewConflictError(
                "Bộ nhãn đang được ghi ở phiên khác. Đợi hoàn tất rồi làm mới. "
                "Nếu ứng dụng trước đã dừng đột ngột, đóng các phiên rà soát trước khi xử lý file khóa."
            ) from exc
        try:
            os.close(descriptor)
            yield
        finally:
            lock_path.unlink(missing_ok=True)


class ReviewStore:
    """Load, review and explicitly save human decisions in one frozen kit."""

    def __init__(self, directory, *, snapshot_loader=None, text_loader=None,
                 coverage_checker=None, storage_root=None):
        self.directory = Path(directory).resolve()
        self.snapshot_loader = snapshot_loader or _snapshot_loader
        self.text_loader = text_loader or _text_loader
        self.coverage_checker = coverage_checker or _coverage_checker
        self.storage_root = storage_root

    def load(self):
        payloads = {name: (self.directory / name).read_bytes() for name in _FILES}
        token = canonical_sha256({name: hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()})
        manifest = json.loads(payloads["corpus_manifest.json"].decode("utf-8-sig"))
        protocol = json.loads(payloads["protocol.json"].decode("utf-8-sig"))
        queries = list(csv.DictReader(io.StringIO(payloads["evaluation_queries.csv"].decode("utf-8-sig"))))
        judgments = list(csv.DictReader(io.StringIO(payloads["relevance_judgments.csv"].decode("utf-8-sig"))))
        if not queries:
            raise EvaluationInputError("Bộ rà soát chưa có truy vấn.")
        snapshot = self.snapshot_loader(manifest.get("corpus_name"))
        validate_frozen_corpus(snapshot, manifest, storage_root=self.storage_root)
        query_by_id = {row["query_id"]: row for row in queries}
        if len(query_by_id) != len(queries):
            raise EvaluationInputError("query_id bị trùng trong bộ rà soát.")
        document_ids = {row["document_id"] for row in snapshot["documents"]}
        seen = set()
        for row in judgments:
            query = query_by_id.get(row.get("query_id"))
            try:
                document_id = int(row.get("document_id", ""))
            except (TypeError, ValueError) as exc:
                raise EvaluationInputError("Mã tài liệu trong bộ nhãn không hợp lệ.") from exc
            if query is None or document_id not in document_ids:
                raise EvaluationInputError("Bộ nhãn tham chiếu truy vấn/tài liệu ngoài corpus đã chốt.")
            if row.get("query_semantic_sha256") != query_semantic_sha256(query):
                raise EvaluationInputError(
                    "Nội dung truy vấn hoặc nhu cầu thông tin đã đổi so với bộ nhãn. "
                    "Tạo bộ nhãn trắng mới và rà soát lại; không tái sử dụng nhãn cũ."
                )
            pair = (row["query_id"], document_id)
            if pair in seen:
                raise EvaluationInputError("Bộ nhãn có cặp truy vấn/tài liệu bị trùng.")
            seen.add(pair)
        if type(protocol.get("assessor_count")) is not int or protocol["assessor_count"] not in {1, 2}:
            raise EvaluationInputError("Quy trình phải khai báo 1 hoặc 2 người gán nhãn.")
        return {"token": token, "manifest": manifest, "protocol": protocol,
                "queries": queries, "judgments": judgments, "snapshot": snapshot}

    @contextmanager
    def _mutation(self, expected_token):
        with _exclusive_write(self.directory):
            current = self.load()  # Revalidate the live corpus before every save.
            if current["token"] != expected_token:
                raise ReviewConflictError("Dữ liệu đã đổi ở phiên khác. Làm mới và kiểm tra lại trước khi lưu.")
            yield current

    def _write_csv(self, name, fields, rows):
        _atomic_write(self.directory / name, _csv_bytes(fields, rows))

    def read_document(self, kit, document_id):
        if type(document_id) is not int or document_id not in {
            row["document_id"] for row in kit["snapshot"]["documents"]
        }:
            raise EvaluationInputError("Tài liệu không thuộc corpus đã chốt.")
        validate_frozen_corpus(self.snapshot_loader(kit["manifest"].get("corpus_name")),
                               kit["manifest"], storage_root=self.storage_root)
        text = self.text_loader(document_id)
        if not isinstance(text, str) or not text.strip():
            raise EvaluationInputError("Không có nội dung gốc để rà soát; chưa được gán nhãn tài liệu này.")
        validate_frozen_corpus(self.snapshot_loader(kit["manifest"].get("corpus_name")),
                               kit["manifest"], storage_root=self.storage_root)
        return text

    def save_assessment(self, expected_token, query_id, document_id, *, assessor,
                        label, evidence="", slot="a"):
        if label not in {"", "0", "1"}:
            raise EvaluationInputError("Nhãn phải là 0, 1 hoặc để trống.")
        if slot not in {"a", "b"}:
            raise EvaluationInputError("Vai trò gán nhãn không hợp lệ.")
        if not isinstance(evidence, str):
            raise EvaluationInputError("Bằng chứng phải là văn bản.")
        name = _human(assessor, "người gán nhãn") if label else ""
        if label == "1" and not evidence.strip():
            raise EvaluationInputError("Nhãn liên quan cần ghi bằng chứng từ nội dung đã đọc.")
        with self._mutation(expected_token) as current:
            protocol = current["protocol"]
            if slot == "b" and protocol["assessor_count"] != 2:
                raise EvaluationInputError("Quy trình này chỉ dùng một người gán nhãn.")
            query = next((row for row in current["queries"] if row["query_id"] == query_id), None)
            if query is None or type(document_id) is not int or document_id not in {
                row["document_id"] for row in current["snapshot"]["documents"]
            }:
                raise EvaluationInputError("Cặp truy vấn/tài liệu không thuộc bộ rà soát.")
            # Full original text must exist even if this was selected outside
            # the initial pool. Raw text is never replaced by processed tokens.
            self.read_document(current, document_id)
            rows = current["judgments"]
            row = next((item for item in rows if item["query_id"] == query_id
                        and int(item["document_id"]) == document_id), None)
            if row is None:
                row = {**dict.fromkeys(JUDGMENT_FIELDS, ""), "query_id": query_id,
                       "query_semantic_sha256": query_semantic_sha256(query),
                       "document_id": str(document_id)}
                rows.append(row)
            other = "b" if slot == "a" else "a"
            if label and row.get(f"label_{other}") in {"0", "1"} and name.casefold() == row.get(f"assessor_{other}", "").strip().casefold():
                raise EvaluationInputError("Hai vai trò phải do hai người độc lập thực hiện.")
            row[f"label_{slot}"] = label
            row[f"assessor_{slot}"] = name
            if protocol["assessor_count"] == 1:
                row["relevant"] = label
                row["evidence"] = evidence.strip() if label else ""
            else:
                # Preserve the first assessor's evidence when the second
                # records an independent decision. Final disagreements remain
                # blank until a human explicitly adjudicates them.
                if evidence.strip():
                    addition = f"{name}: {evidence.strip()}"
                    existing = row.get("evidence", "").strip()
                    row["evidence"] = f"{existing}\n{addition}".strip() if addition not in existing.splitlines() else existing
                a, b = row.get("label_a", ""), row.get("label_b", "")
                row["relevant"] = a if a in {"0", "1"} and a == b else ""
            row["adjudicator"] = ""
            row["resolution"] = ""
            row["labeled_at"] = _utc_now() if row.get("label_a") or row.get("label_b") else ""
            positions = {query["query_id"]: i for i, query in enumerate(current["queries"])}
            rows.sort(key=lambda item: (positions[item["query_id"]], int(item["document_id"])))
            self._write_csv("relevance_judgments.csv", JUDGMENT_FIELDS, rows)

    def adjudicate(self, expected_token, query_id, document_id, *, relevant, adjudicator, resolution):
        if relevant not in {"0", "1"}:
            raise EvaluationInputError("Người phân xử phải chọn nhãn cuối cùng 0 hoặc 1.")
        name = _human(adjudicator, "người phân xử")
        if not isinstance(resolution, str) or not resolution.strip():
            raise EvaluationInputError("Cần ghi lý do giải quyết bất đồng.")
        with self._mutation(expected_token) as current:
            if current["protocol"]["assessor_count"] != 2:
                raise EvaluationInputError("Phân xử chỉ áp dụng với quy trình hai người gán nhãn.")
            self.read_document(current, document_id)
            row = next((item for item in current["judgments"] if item["query_id"] == query_id
                        and int(item["document_id"]) == document_id), None)
            if row is None or row.get("label_a") not in {"0", "1"} or row.get("label_b") not in {"0", "1"} or row["label_a"] == row["label_b"]:
                raise EvaluationInputError("Chỉ phân xử khi hai người đã gán nhãn khác nhau.")
            row.update(relevant=relevant, adjudicator=name, resolution=resolution.strip(), labeled_at=_utc_now())
            self._write_csv("relevance_judgments.csv", JUDGMENT_FIELDS, current["judgments"])

    def save_query_review(self, expected_token, query_id, *, author, reviewer, approved):
        if type(approved) is not bool:
            raise EvaluationInputError("Trạng thái duyệt truy vấn không hợp lệ.")
        if not isinstance(author, str) or not isinstance(reviewer, str):
            raise EvaluationInputError("Tên người soạn và duyệt phải là văn bản.")
        if approved:
            author, reviewer = _human(author, "người soạn truy vấn"), _human(reviewer, "người duyệt truy vấn")
        with self._mutation(expected_token) as current:
            row = next((item for item in current["queries"] if item["query_id"] == query_id), None)
            if row is None:
                raise EvaluationInputError("Không tìm thấy truy vấn cần duyệt.")
            row.update(author=author.strip(), review_status="approved" if approved else "draft",
                       reviewed_by=reviewer if approved else "", reviewed_at=_utc_now() if approved else "")
            self._write_csv("evaluation_queries.csv", QUERY_FIELDS, current["queries"])

    def save_protocol_review(self, expected_token, *, reviewer, approved, independent_content_review,
                             disagreement_policy):
        if type(approved) is not bool or type(independent_content_review) is not bool:
            raise EvaluationInputError("Trạng thái duyệt quy trình không hợp lệ.")
        if approved and not independent_content_review:
            raise EvaluationInputError("Chỉ phê duyệt khi đã xác nhận gán nhãn từ nội dung, độc lập với điểm/thứ hạng.")
        name = _human(reviewer, "người duyệt quy trình") if approved else ""
        if not isinstance(disagreement_policy, str) or not disagreement_policy.strip():
            raise EvaluationInputError("Cần mô tả cách xử lý nhãn/bất đồng.")
        with self._mutation(expected_token) as current:
            protocol = current["protocol"]
            protocol.update(status="approved" if approved else "draft",
                            independent_of_retrieval_scores=independent_content_review,
                            reviewed_by=name, reviewed_at=_utc_now() if approved else "",
                            disagreement_policy=disagreement_policy.strip())
            payload = (json.dumps(protocol, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            _atomic_write(self.directory / "protocol.json", payload)

    @staticmethod
    def progress(kit):
        count = kit["protocol"]["assessor_count"]
        rows = kit["judgments"]
        completed = sum(row.get("relevant") in {"0", "1"} and row.get("label_a") in {"0", "1"}
                        and (count == 1 or row.get("label_b") in {"0", "1"}) for row in rows)
        disagreements = sum(row.get("label_a") in {"0", "1"} and row.get("label_b") in {"0", "1"}
                            and row["label_a"] != row["label_b"] and row.get("relevant") not in {"0", "1"} for row in rows)
        return {"query_count": len(kit["queries"]),
                "approved_queries": sum(row.get("review_status") == "approved" for row in kit["queries"]),
                "pair_count": len(rows), "completed_pairs": completed,
                "positive_pairs": sum(row.get("relevant") == "1" for row in rows),
                "unresolved_disagreements": disagreements}

    def check_readiness(self, expected_token):
        current = self.load()
        if current["token"] != expected_token:
            raise ReviewConflictError("Bộ nhãn đã đổi. Làm mới trước khi kiểm tra.")
        relevance = validate_evaluation_inputs(current["snapshot"], current["manifest"], current["protocol"],
                                              current["queries"], current["judgments"], storage_root=self.storage_root)
        if current["protocol"]["judgment_scope"] == "pooled_top20":
            pools = self.coverage_checker(current["snapshot"], current["queries"])
            missing = {qid: len(set(ids) - relevance.judged_document_ids[qid])
                       for qid, ids in pools.items() if set(ids) - relevance.judged_document_ids[qid]}
            if missing:
                raise EvaluationInputError(f"Chưa đủ nhãn cho vùng kiểm tra Top-20: {missing}. Không được xem cặp chưa gán là không liên quan.")
        validate_frozen_corpus(self.snapshot_loader(current["manifest"].get("corpus_name")),
                               current["manifest"], storage_root=self.storage_root)
        if self.load()["token"] != expected_token:
            raise ReviewConflictError("Bộ nhãn đổi trong khi kiểm tra. Làm mới rồi thử lại.")
        return self.progress(current)
