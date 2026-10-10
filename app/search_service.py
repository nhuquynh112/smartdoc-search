"""Application integration for the unchanged data and retrieval services.

The catalog cache is deliberately excluded from freshness checks. The shared
lock serializes UI search/rebuild operations; it cannot lock external database
writers, so a second uncached check also rejects changes during an operation.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from threading import RLock
from typing import Any

from smartdoc.index_manager import IndexManager, ManagedIndex, NoActiveIndexError
from smartdoc.inverted_index import get_candidates, get_postings
from smartdoc.retrieval_engine import InvalidRetrievalInputError, MAX_TOP_K, RetrievalEngine


_OPERATIONS_LOCK = RLock()
DEFAULT_INDEX_ROOT = Path(__file__).resolve().parents[1] / "data" / "tv2_index"


def _snapshot_loader(corpus_name: str | None) -> Mapping[str, Any]:
    from smartdoc.ingestion import load_corpus_snapshot
    return load_corpus_snapshot(corpus_name)


def _metadata_loader(document_ids: list[int]) -> list[dict]:
    from smartdoc.ingestion import get_documents_by_ids
    return get_documents_by_ids(document_ids)


class _PinnedIndex:
    """Keep explanation's two index reads on the same immutable version."""

    def __init__(self, managed: ManagedIndex) -> None:
        self.managed = managed

    def load_active(self) -> ManagedIndex:
        return self.managed


class SearchService:
    """Bridge the Streamlit UI to versioned TF-IDF without changing TV1/TV2.

    Injectable loaders and preprocessing support isolated integration tests;
    production defaults always call the real data services.
    """

    def __init__(
        self,
        index_root: str | Path | None = None,
        corpus_name: str | None = None,
        *,
        snapshot_loader: Callable[[str | None], Mapping[str, Any]] | None = None,
        metadata_loader: Callable[[list[int]], list[dict]] | None = None,
        preprocessing_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.corpus_name = corpus_name
        self.snapshot_loader = snapshot_loader or _snapshot_loader
        self.metadata_loader = metadata_loader or _metadata_loader
        self.preprocessing_fn = preprocessing_fn
        self.mutation_lock = _OPERATIONS_LOCK
        self.index_root = Path(index_root).resolve() if index_root is not None else DEFAULT_INDEX_ROOT
        self.index_manager = IndexManager(self.index_root, snapshot_loader=self.snapshot_loader)

    def _inspect(self) -> tuple[dict[str, Any], ManagedIndex | None, list[dict]]:
        state: dict[str, Any] = {
            "status": "index_unavailable", "message": "Chỉ mục tìm kiếm chưa sẵn sàng.",
            "index_version": None, "corpus_revision": None, "document_count": 0,
        }
        try:
            snapshot = self.snapshot_loader(self.corpus_name)
            if not isinstance(snapshot, Mapping):
                raise ValueError("Snapshot must be a mapping.")
            revision = snapshot["corpus_revision"]
            if isinstance(revision, bool) or not isinstance(revision, int):
                raise ValueError("Corpus revision must be an integer.")
            preprocessing = snapshot["preprocessing"]
            if not isinstance(preprocessing, Mapping):
                raise ValueError("Preprocessing metadata must be a mapping.")
            fingerprint = preprocessing.get("fingerprint")
            if fingerprint is not None and not isinstance(fingerprint, str):
                raise ValueError("Invalid preprocessing fingerprint.")
            documents = snapshot["documents"]
            if isinstance(documents, (str, bytes, Mapping)):
                raise ValueError("Documents must be a sequence of mappings.")
            documents = list(documents)
            if any(not isinstance(doc, Mapping) for doc in documents):
                raise ValueError("Every document must be a mapping.")
            ids = [doc["document_id"] for doc in documents]
            if any(isinstance(doc_id, bool) or not isinstance(doc_id, int) for doc_id in ids):
                raise ValueError("Document IDs must be integers.")
            if len(set(ids)) != len(ids):
                raise ValueError("Document IDs must be unique.")
            selector = snapshot.get("corpus_name") or self.corpus_name
            state.update(corpus_revision=revision, document_count=len(documents))
        except Exception as exc:
            state["message"] = f"Không thể kiểm tra dữ liệu hiện tại: {exc}"
            return state, None, []
        try:
            managed = self.index_manager.load_active()
        except NoActiveIndexError:
            if not documents:
                state.update(status="empty_corpus", message="Thư viện hiện chưa có tài liệu.")
            return state, None, documents
        except Exception as exc:
            state["message"] = f"Không thể nạp chỉ mục: {exc}"
            return state, None, documents
        state["index_version"] = managed.version_id
        artifacts = managed.artifacts
        if (artifacts.corpus_revision != revision
                or artifacts.preprocessing_fingerprint != fingerprint
                or artifacts.corpus_name != selector
                or set(artifacts.ordered_document_ids) != set(ids)):
            state.update(status="stale_index", message="Dữ liệu đã thay đổi; cần xây lại chỉ mục.")
        elif not documents:
            state.update(status="empty_corpus", message="Thư viện hiện chưa có tài liệu.")
        else:
            state.update(status="ok", message="Chỉ mục đã đồng bộ với dữ liệu hiện tại.")
        return state, managed, documents

    def status(self) -> dict[str, Any]:
        with _OPERATIONS_LOCK:
            return self._inspect()[0]

    def _engine(self, managed: ManagedIndex | None = None) -> RetrievalEngine:
        return RetrievalEngine(
            index_manager=_PinnedIndex(managed) if managed is not None else self.index_manager,
            snapshot_loader=self.snapshot_loader,
            preprocessing_fn=self.preprocessing_fn,
            corpus_name=self.corpus_name,
        )

    @staticmethod
    def _empty_response(state: dict[str, Any]) -> dict[str, Any]:
        return {**state, "results": []}

    def _verify_response(self, response: dict, expected_version: str | None) -> dict | None:
        state, _, _ = self._inspect()
        if state["status"] != "ok":
            return state
        if (state["index_version"] != expected_version
                or response.get("index_version") != expected_version
                or response.get("corpus_revision") != state["corpus_revision"]):
            return {**state, "status": "stale_index",
                    "message": "Phiên bản chỉ mục đã thay đổi; hãy tìm kiếm lại."}
        return None

    def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        with _OPERATIONS_LOCK:
            if not isinstance(query, str):
                raise InvalidRetrievalInputError("query must be a string")
            if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= MAX_TOP_K:
                raise InvalidRetrievalInputError("top_k must be an integer from 1 to 20")
            # Let the public engine validate input and preserve empty-query behavior.
            if not query.strip():
                return self._engine().search_query(query, top_k)
            state, managed, documents = self._inspect()
            if state["status"] != "ok":
                return self._empty_response(state)
            response = self._engine(managed).search_query(query, top_k)
            if response["status"] not in {"ok", "oov_query"}:
                return response
            hits = response["results"]
            try:
                ids = [hit["document_id"] for hit in hits]
                metadata = self.metadata_loader(ids) if ids else []
                by_id = {row["document_id"]: row for row in metadata}
                if len(by_id) != len(metadata) or set(by_id) != set(ids):
                    raise LookupError("Returned document metadata does not match search results.")
                snapshot_by_id = {row["document_id"]: row for row in documents}
                enriched = [{**snapshot_by_id[hit["document_id"]],
                             **by_id[hit["document_id"]], **hit} for hit in hits]
            except Exception as exc:
                return self._empty_response({**state, "status": "index_unavailable",
                                             "message": f"Không thể đọc metadata kết quả: {exc}"})
            mismatch = self._verify_response(response, state["index_version"])
            if mismatch:
                return self._empty_response(mismatch)
            return {**response, "results": enriched}

    def rebuild(self) -> dict[str, Any]:
        with _OPERATIONS_LOCK:
            try:
                built = self.index_manager.build_and_activate(self.corpus_name)
            except Exception as exc:
                state = self._inspect()[0]
                return {**state, "status": "rebuild_failed", "rebuilt": False,
                        "message": f"Xây lại chỉ mục thất bại: {exc}"}
            state = self._inspect()[0]
            rebuilt = state["status"] in {"ok", "empty_corpus"} and state["index_version"] == built.version_id
            if not rebuilt and state["status"] == "ok":
                state.update(status="stale_index", message="Chỉ mục đã đổi trong khi xây dựng; hãy thử lại.")
            return {**state, "rebuilt": rebuilt}

    def explain(
        self, query: str, document_id: int, expected_version: str | None = None,
    ) -> dict[str, Any]:
        with _OPERATIONS_LOCK:
            state, managed, _ = self._inspect()
            empty = {"document_id": document_id, "query_tokens": [], "matched_terms": [],
                     "score": None, "posting_lists": {}, "candidate_ids": []}
            if state["status"] != "ok":
                return {**state, **empty}
            if expected_version is not None and state["index_version"] != expected_version:
                return {**state, **empty, "status": "stale_index",
                        "message": "Kết quả thuộc phiên bản cũ; hãy tìm kiếm lại."}
            response = self._engine(managed).explain_result(query, document_id)
            if response["status"] != "ok":
                return {**response, "posting_lists": {}, "candidate_ids": []}
            mismatch = self._verify_response(response, state["index_version"])
            if mismatch:
                return {**mismatch, **empty}
            terms = list(dict.fromkeys(response["query_tokens"]))
            return {**response,
                    "posting_lists": {term: list(get_postings(managed.inverted_index, term)) for term in terms},
                    "candidate_ids": list(get_candidates(managed.inverted_index, terms))}
