"""TV3 metrics and audited evaluation inputs (no database or model imports).

Only human-reviewed labels are accepted. Synthetic labels belong exclusively
in tests and are never exported as experimental evidence.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

MIN_QUERIES = 20
MRR_DEPTH = 20
QUERY_FIELDS = (
    "query_id", "query", "information_need", "category", "seed_document_ids",
    "provenance", "author", "review_status", "reviewed_by", "reviewed_at",
)
JUDGMENT_FIELDS = (
    "query_id", "query_semantic_sha256", "document_id", "label_a", "assessor_a", "label_b", "assessor_b",
    "relevant", "adjudicator", "resolution", "evidence", "labeled_at",
)


class EvaluationInputError(ValueError):
    """An experiment would be incomplete or inconsistent with its frozen corpus."""


class ValidatedJudgments(dict):
    """Relevant ID sets plus the actual human-judged coverage for safe pooling."""

    def __init__(self, relevant, judged_ids, scope):
        super().__init__(relevant)
        self.judged_document_ids = judged_ids
        self.judgment_scope = scope


def canonical_sha256(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def query_semantic_sha256(query) -> str:
    """Bind a judgment to the exact question/need that the human read."""
    fields = ("query_id", "query", "information_need")
    for field in fields:
        _required_text(query, field, "Query semantics")
    return canonical_sha256({field: query[field] for field in fields})


def _snapshot_rows(snapshot):
    if not isinstance(snapshot, dict):
        raise EvaluationInputError("Snapshot must be a JSON object.")
    rows = snapshot.get("documents")
    if not isinstance(rows, list) or not rows:
        raise EvaluationInputError("The frozen corpus must contain documents.")
    ids = []
    for row in rows:
        if not isinstance(row, dict):
            raise EvaluationInputError("Each corpus document must be a JSON object.")
        doc_id = row.get("document_id")
        if isinstance(doc_id, bool) or not isinstance(doc_id, int) or doc_id <= 0:
            raise EvaluationInputError("Document IDs must be positive integers.")
        if not isinstance(row.get("clean_text"), str) or not row["clean_text"].strip():
            raise EvaluationInputError(f"Document {doc_id} has no searchable text.")
        ids.append(doc_id)
    if len(ids) != len(set(ids)):
        raise EvaluationInputError("Duplicate document IDs in corpus.")
    revision = snapshot.get("corpus_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise EvaluationInputError("corpus_revision must be a nonnegative integer.")
    preprocessing = snapshot.get("preprocessing")
    if not isinstance(preprocessing, dict):
        raise EvaluationInputError("Snapshot preprocessing must be a JSON object.")
    fingerprint = preprocessing.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise EvaluationInputError("A preprocessing fingerprint is required.")
    for row in rows:
        if row.get("preprocessing_version") != fingerprint:
            raise EvaluationInputError(
                f"Document {row['document_id']} preprocessing_version differs from the corpus fingerprint. "
                "Export a corpus with verified, consistent preprocessing."
            )
    return sorted(rows, key=lambda row: row["document_id"])


def corpus_manifest(snapshot, *, storage_root=None):
    """Freeze corpus identity separately from the preprocessed retrieval inputs.

    Identity hashes exclude clean_text, revision and preprocessing, so the same
    document selection can be compared across preprocessing variants. If the
    originals are absent, the identity hash describes source IDs/metadata only;
    retrieval_input_sha256 still freezes every actual clean_text byte.
    """
    rows = _snapshot_rows(snapshot)
    identities = []
    missing_originals = []
    root = Path(storage_root).resolve() if storage_root else None
    for row in rows:
        identity = {key: row.get(key) for key in (
            "document_id", "title", "source_uri", "corpus_name", "category", "dataset_id",
        )}
        identities.append(identity)
        if root and row.get("storage_ref"):
            path = (root / row["storage_ref"]).resolve()
            if not path.is_relative_to(root):
                raise EvaluationInputError("An original file reference escapes storage_root.")
            if path.is_file():
                identity["original_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                missing_originals.append(row["document_id"])
        else:
            missing_originals.append(row["document_id"])
    # Keep the preprocessing-independent identity stable when originals are
    # restored later. Available byte hashes are supplementary verification.
    independent_identity = [
        {key: value for key, value in row.items() if key != "original_sha256"}
        for row in identities
    ]
    retrieval_inputs = {
        "corpus_name": snapshot.get("corpus_name"),
        "corpus_revision": snapshot["corpus_revision"],
        "preprocessing": snapshot["preprocessing"],
        "documents": [{key: row.get(key) for key in (
            "document_id", "title", "clean_text", "source_uri", "preprocessing_version",
        )} for row in rows],
    }
    return {
        "format_version": 1,
        "corpus_name": snapshot.get("corpus_name"),
        "corpus_revision": snapshot["corpus_revision"],
        "preprocessing_fingerprint": snapshot["preprocessing"]["fingerprint"],
        "document_count": len(rows),
        "corpus_identity_sha256": canonical_sha256(independent_identity),
        "identity_hash_basis": "sorted source IDs and metadata; excludes clean_text and preprocessing",
        "retrieval_input_sha256": canonical_sha256(retrieval_inputs),
        "documents": identities,
        "missing_original_document_ids": missing_originals,
        "limitation": (
            "Some original files are unavailable. Identity hash verifies source IDs/metadata, "
            "not original bytes; retrieval_input_sha256 freezes all indexed clean_text."
            if missing_originals else "Original file SHA-256 hashes are also recorded."
        ),
    }


def validate_frozen_corpus(snapshot, manifest, *, storage_root=None):
    actual = corpus_manifest(snapshot, storage_root=storage_root)
    for field in (
        "format_version", "corpus_name", "corpus_revision", "preprocessing_fingerprint",
        "document_count", "corpus_identity_sha256", "retrieval_input_sha256",
    ):
        if manifest.get(field) != actual[field]:
            raise EvaluationInputError(f"Frozen corpus mismatch: {field}. Prepare/review a new experiment.")
    frozen_rows = manifest.get("documents")
    if not isinstance(frozen_rows, list) or len(frozen_rows) != actual["document_count"]:
        raise EvaluationInputError("Frozen manifest document list is incomplete.")
    frozen_by_id = {row.get("document_id"): row for row in frozen_rows}
    if len(frozen_by_id) != len(frozen_rows):
        raise EvaluationInputError("Frozen manifest has duplicate document IDs.")
    if set(frozen_by_id) != {row["document_id"] for row in actual["documents"]}:
        raise EvaluationInputError("Frozen manifest document IDs differ from the snapshot.")
    for row in actual["documents"]:
        frozen = frozen_by_id[row["document_id"]]
        for key, value in row.items():
            if key != "original_sha256" and frozen.get(key) != value:
                raise EvaluationInputError("Frozen manifest document metadata was modified.")
        if frozen.get("original_sha256") and row.get("original_sha256") != frozen["original_sha256"]:
            raise EvaluationInputError(f"Original file missing/changed: {row['document_id']}.")
    return actual


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, fields, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _required_text(row, field, context):
    text = row.get(field)
    if not isinstance(text, str) or not text.strip():
        raise EvaluationInputError(f"{context}: missing {field}.")
    return text.strip()


def _human_name(row, field, context):
    name = _required_text(row, field, context)
    if name.casefold() in {"ai", "chatgpt", "codex", "auto", "automatic", "todo", "unknown"}:
        raise EvaluationInputError(f"{context}: {field} must identify a human assessor.")
    return name


def _timestamp(row, field, context):
    value = _required_text(row, field, context)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvaluationInputError(f"{context}: {field} must be ISO 8601.") from exc
    if parsed.tzinfo is None:
        raise EvaluationInputError(f"{context}: {field} must include a UTC offset.")


def validate_evaluation_inputs(snapshot, manifest, protocol, queries, judgments, *, storage_root=None):
    """Require >=20 reviewed queries and declared exhaustive or pooled labels.

    Pooled labels are checked again against every actual returned Top-20 ID
    by the benchmark before any metric is computed. No recall is inferred.
    """
    validate_frozen_corpus(snapshot, manifest, storage_root=storage_root)
    if protocol.get("status") != "approved":
        raise EvaluationInputError("Evaluation protocol is draft; human review is required.")
    if protocol.get("labeling_method") != "human_content_review" or protocol.get("independent_of_retrieval_scores") is not True:
        raise EvaluationInputError("Labels must come from human content review without cosine scores or rankings.")
    declared_minimum = protocol.get("minimum_queries")
    if (type(declared_minimum) is not int or declared_minimum < MIN_QUERIES or protocol.get("mrr_depth") != MRR_DEPTH
            or protocol.get("precision_denominator") != 5):
        raise EvaluationInputError("Protocol must specify >=20 queries, Precision denominator 5, and MRR@20.")
    for field in ("corpus_identity_sha256", "retrieval_input_sha256"):
        if protocol.get(field) != manifest.get(field):
            raise EvaluationInputError(f"Protocol mismatch: {field}.")
    _human_name(protocol, "reviewed_by", "Protocol")
    _required_text(protocol, "disagreement_policy", "Protocol")
    _timestamp(protocol, "reviewed_at", "Protocol")
    scope = protocol.get("judgment_scope")
    if scope not in {"exhaustive", "pooled_top20"}:
        raise EvaluationInputError("Declare judgment_scope as exhaustive or pooled_top20.")
    assessor_count = protocol.get("assessor_count")
    if type(assessor_count) is not int or assessor_count not in {1, 2}:
        raise EvaluationInputError("assessor_count must be 1 or 2.")
    if len(queries) < declared_minimum:
        raise EvaluationInputError(f"At least {declared_minimum} reviewed metric queries are required.")
    doc_ids = {row["document_id"] for row in snapshot["documents"]}
    query_ids = set()
    query_texts = set()
    semantic_hashes = {}
    for query in queries:
        qid = _required_text(query, "query_id", "Query")
        if qid in query_ids:
            raise EvaluationInputError(f"Duplicate query_id: {qid}.")
        query_ids.add(qid)
        semantic_hashes[qid] = query_semantic_sha256(query)
        for field in ("query", "information_need", "provenance"):
            _required_text(query, field, qid)
        normalized = " ".join(query["query"].casefold().split())
        if normalized in query_texts:
            raise EvaluationInputError(f"{qid}: duplicate query text would inflate the experiment.")
        query_texts.add(normalized)
        if query.get("review_status") != "approved":
            raise EvaluationInputError(f"{qid} is a draft query; review or remove it before measuring.")
        for field in ("author", "reviewed_by"):
            _human_name(query, field, qid)
        _timestamp(query, "reviewed_at", qid)
        seeds = query.get("seed_document_ids", "").strip()
        if seeds:
            try:
                parsed_seeds = {int(value) for value in seeds.split(";")}
            except ValueError as exc:
                raise EvaluationInputError(f"{qid}: seed IDs must be semicolon-separated integers.") from exc
            if not parsed_seeds <= doc_ids:
                raise EvaluationInputError(f"{qid}: unknown seed document ID.")
    relevant = {qid: set() for qid in query_ids}
    judged_ids = {qid: set() for qid in query_ids}
    seen = set()
    for judgment in judgments:
        qid = judgment.get("query_id")
        try:
            doc_id = int(judgment.get("document_id", ""))
        except (ValueError, TypeError) as exc:
            raise EvaluationInputError("Judgment document_id must be an integer.") from exc
        context = f"Judgment {qid}/{doc_id}"
        if qid not in query_ids or doc_id not in doc_ids:
            raise EvaluationInputError(f"{context}: unknown query or document ID.")
        if judgment.get("query_semantic_sha256") != semantic_hashes[qid]:
            raise EvaluationInputError(
                f"{context}: query semantics changed or the binding hash is missing. "
                "Prepare a new blank kit for the edited query/need and reassess; do not reuse old labels."
            )
        if (qid, doc_id) in seen:
            raise EvaluationInputError(f"{context}: duplicate judgment.")
        seen.add((qid, doc_id))
        required_labels = ("label_a", "relevant") if assessor_count == 1 else ("label_a", "label_b", "relevant")
        if any(judgment.get(field) not in {"0", "1"} for field in required_labels):
            raise EvaluationInputError(f"{context}: incomplete labels; use 0 or 1 for required human labels and final relevance.")
        assessor_a = _human_name(judgment, "assessor_a", context)
        if assessor_count == 1:
            if judgment["relevant"] != judgment["label_a"]:
                _human_name(judgment, "adjudicator", context)
                _required_text(judgment, "resolution", context)
        else:
            assessor_b = _human_name(judgment, "assessor_b", context)
            if assessor_a.casefold() == assessor_b.casefold():
                raise EvaluationInputError(f"{context}: two independent human assessors are required.")
            if judgment["label_a"] == judgment["label_b"]:
                if judgment["relevant"] != judgment["label_a"]:
                    raise EvaluationInputError(f"{context}: final label conflicts with agreed labels.")
            else:
                _human_name(judgment, "adjudicator", context)
                _required_text(judgment, "resolution", context)
        # Brief positive evidence supports auditing. Negative evidence notes
        # are optional, avoiding thousands of repetitive "not relevant" notes.
        if judgment["relevant"] == "1":
            _required_text(judgment, "evidence", context)
        _timestamp(judgment, "labeled_at", context)
        judged_ids[qid].add(doc_id)
        if judgment["relevant"] == "1":
            relevant[qid].add(doc_id)
    required = len(query_ids) * len(doc_ids)
    if scope == "exhaustive" and len(seen) != required:
        raise EvaluationInputError(f"Incomplete judgments: {len(seen)}/{required} query-document pairs.")
    empty = sorted(qid for qid, ids in relevant.items() if not ids)
    if empty:
        if scope == "pooled_top20":
            raise EvaluationInputError(
                f"No known relevant document in the judged pool for {', '.join(empty)}. "
                "Expand independent content assessment beyond Top-20 and add positive judgments if found; "
                "keep missed queries in the metric set with zero retrieved hits. "
                "Only move a query to behavior tests after confirming no relevant document exists in the corpus."
            )
        raise EvaluationInputError(f"No relevant document in the exhaustively judged corpus for {', '.join(empty)}; report these as behavior tests separately.")
    return ValidatedJudgments(relevant, judged_ids, scope)


def _ranking(ids):
    ids = list(ids)
    if len(ids) != len(set(ids)):
        raise EvaluationInputError("Ranking contains duplicate document IDs.")
    return ids


def precision_at_5(ranked_ids, relevant_ids):
    """Always divide by five, even with zero, one or four retrieved results."""
    return len(set(_ranking(ranked_ids)[:5]) & set(relevant_ids)) / 5


def reciprocal_rank_at_20(ranked_ids, relevant_ids):
    relevant = set(relevant_ids)
    return next((1 / rank for rank, doc_id in enumerate(_ranking(ranked_ids)[:MRR_DEPTH], 1)
                 if doc_id in relevant), 0.0)


def summarize_metrics(per_query):
    if not per_query:
        raise EvaluationInputError("Cannot average an empty experiment.")
    return {
        "query_count": len(per_query),
        "precision_at_5": sum(row["precision_at_5"] for row in per_query) / len(per_query),
        "mrr_at_20": sum(row["reciprocal_rank_at_20"] for row in per_query) / len(per_query),
    }


def latency_summary(samples):
    if not samples or any(not math.isfinite(value) or value < 0 for value in samples):
        raise EvaluationInputError("Latency samples must be nonempty finite nonnegative milliseconds.")
    values = sorted(samples)
    # Nearest-rank percentile; defined explicitly for reproducibility.
    return {"count": len(values), "mean_ms": sum(values) / len(values),
            "p50_ms": values[math.ceil(0.50 * len(values)) - 1],
            "p95_ms": values[math.ceil(0.95 * len(values)) - 1],
            "min_ms": values[0], "max_ms": values[-1]}
