"""Public retrieval API for SmartDoc Search TV2.

This module coordinates TV1 preprocessing, the active TV2 index, and query-time
ranking. It returns a stable response object for TV3 and never returns results
from an index whose revision or preprocessing fingerprint differs from the
current TV1 snapshot.

Note: the current TV1 contract exposes a full corpus snapshot rather than a
lightweight revision-only endpoint. The default implementation therefore loads
that snapshot per search to guarantee freshness; this can be optimized later
if TV1 provides a trusted lightweight revision API.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .index_manager import (
    IndexManager,
    IndexManagerError,
    NoActiveIndexError,
    SnapshotLoadError,
)
from .search_engine import create_search_engine, search
from .tfidf_engine import TfidfEngineError

DEFAULT_TOP_K = 5
MAX_TOP_K = 20

VALID_STATUSES = {
    "ok",
    "empty_query",
    "oov_query",
    "empty_corpus",
    "index_unavailable",
    "stale_index",
}


class RetrievalEngineError(RuntimeError):
    """Base exception for Retrieval Engine failures."""


class InvalidRetrievalInputError(RetrievalEngineError, ValueError):
    """Raised when public search arguments are invalid."""


def _load_current_snapshot(corpus_name: str | None = None) -> Mapping[str, Any]:
    """Load current corpus metadata through TV1's public snapshot API."""
    try:
        from .ingestion import load_corpus_snapshot
    except Exception as exc:
        raise SnapshotLoadError(
            "Could not import TV1 load_corpus_snapshot from smartdoc.ingestion"
        ) from exc

    try:
        snapshot = load_corpus_snapshot(corpus_name=corpus_name)
    except Exception as exc:
        raise SnapshotLoadError(f"TV1 corpus snapshot failed: {exc}") from exc

    if not isinstance(snapshot, Mapping):
        raise SnapshotLoadError("load_corpus_snapshot() must return a mapping")
    return snapshot


def _response(
    status: str,
    message: str,
    *,
    results: list[dict[str, int | float]] | None = None,
    index_version: str | None = None,
    corpus_revision: int | None = None,
) -> dict[str, Any]:
    """Build the response shape shared with TV3."""
    return {
        "status": status,
        "message": message,
        "results": results if results is not None else [],
        "index_version": index_version,
        "corpus_revision": corpus_revision,
    }


class RetrievalEngine:
    """Facade used by TV3.

    Args:
        index_manager: Optional manager; injectable for tests.
        snapshot_loader: Optional current-snapshot loader, called with corpus_name.
        preprocessing_fn: Optional preprocessing function; defaults to TV1's
            ``smartdoc.preprocessing.preprocess_text``.
        corpus_name: Optional corpus selector passed to TV1.
    """

    def __init__(
        self,
        index_manager: IndexManager | None = None,
        *,
        snapshot_loader: Callable[[str | None], Mapping[str, Any]] | None = None,
        preprocessing_fn: Callable[[str], str] | None = None,
        corpus_name: str | None = None,
    ) -> None:
        self.index_manager = index_manager or IndexManager()
        self.snapshot_loader = snapshot_loader or _load_current_snapshot
        self.preprocessing_fn = preprocessing_fn or self._default_preprocess
        self.corpus_name = corpus_name

    @staticmethod
    def _default_preprocess(text: str) -> str:
        # Lazy import keeps the module importable in isolated engine tests.
        from .preprocessing import preprocess_text
        return preprocess_text(text)

    def _current_snapshot(self) -> tuple[list[Mapping[str, Any]], int, str | None, str | None]:
        try:
            snapshot = self.snapshot_loader(self.corpus_name)
        except Exception as exc:
            raise SnapshotLoadError(f"Could not load current corpus snapshot: {exc}") from exc

        if not isinstance(snapshot, Mapping):
            raise SnapshotLoadError("Current corpus snapshot must be a mapping")
        required = ("documents", "corpus_revision", "preprocessing")
        missing = [key for key in required if key not in snapshot]
        if missing:
            raise SnapshotLoadError(
                f"Current corpus snapshot is missing: {', '.join(missing)}"
            )

        raw_documents = snapshot["documents"]
        if isinstance(raw_documents, (str, bytes, Mapping)):
            raise SnapshotLoadError("Snapshot documents must be an iterable of document mappings")
        try:
            documents = list(raw_documents)
        except TypeError as exc:
            raise SnapshotLoadError("Snapshot documents must be iterable") from exc

        revision = snapshot["corpus_revision"]
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise SnapshotLoadError("Snapshot corpus_revision must be an integer")

        preprocessing = snapshot["preprocessing"]
        if not isinstance(preprocessing, Mapping):
            raise SnapshotLoadError("Snapshot preprocessing metadata must be a mapping")
        fingerprint = preprocessing.get("fingerprint")
        if fingerprint is not None and not isinstance(fingerprint, str):
            raise SnapshotLoadError("Snapshot preprocessing fingerprint must be a string or None")

        snapshot_corpus_name = snapshot.get("corpus_name")
        if snapshot_corpus_name is not None and not isinstance(snapshot_corpus_name, str):
            raise SnapshotLoadError("Snapshot corpus_name must be a string or None")
        resolved_corpus_name = snapshot_corpus_name or self.corpus_name

        return documents, revision, fingerprint, resolved_corpus_name

    def search_query(self, query: str, top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
        """Search the current corpus and return the TV3 response contract.

        Valid statuses are: ok, empty_query, oov_query, empty_corpus,
        index_unavailable, stale_index. Invalid argument types/ranges raise
        InvalidRetrievalInputError instead of being confused with search states.
        """
        if not isinstance(query, str):
            raise InvalidRetrievalInputError("query must be a string")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= MAX_TOP_K:
            raise InvalidRetrievalInputError("top_k must be an integer from 1 to 20")

        try:
            processed_query = self.preprocessing_fn(query)
        except Exception as exc:
            raise RetrievalEngineError(f"Query preprocessing failed: {exc}") from exc
        if not isinstance(processed_query, str):
            raise RetrievalEngineError("preprocess_text(query) must return a string")
        if not processed_query.strip():
            return _response("empty_query", "Vui lòng nhập nội dung tìm kiếm.")

        # We must inspect the current TV1 snapshot; the active manifest alone
        # cannot tell whether the database changed after the index was built.
        try:
            documents, current_revision, current_fingerprint, current_corpus_name = (
                self._current_snapshot()
            )
        except Exception as exc:
            return _response(
                "index_unavailable",
                f"Không thể kiểm tra trạng thái corpus hiện tại: {exc}",
            )

        if not documents:
            return _response(
                "empty_corpus",
                "Corpus hiện chưa có tài liệu để tìm kiếm.",
                corpus_revision=current_revision,
            )

        try:
            managed_index = self.index_manager.load_active()
        except NoActiveIndexError:
            return _response(
                "index_unavailable",
                "Chỉ mục tìm kiếm chưa sẵn sàng.",
                corpus_revision=current_revision,
            )
        except IndexManagerError as exc:
            return _response(
                "index_unavailable",
                f"Không thể nạp chỉ mục tìm kiếm: {exc}",
                corpus_revision=current_revision,
            )
        except Exception as exc:
            return _response(
                "index_unavailable",
                f"Lỗi khi nạp chỉ mục tìm kiếm: {exc}",
                corpus_revision=current_revision,
            )

        active_artifacts = managed_index.artifacts
        active_revision = active_artifacts.corpus_revision
        active_fingerprint = active_artifacts.preprocessing_fingerprint
        active_corpus_name = active_artifacts.corpus_name

        # Compare against the current TV1 snapshot before ever serving results.
        if (
            active_revision != current_revision
            or active_fingerprint != current_fingerprint
            or active_corpus_name != current_corpus_name
        ):
            return _response(
                "stale_index",
                "Chỉ mục không đồng bộ với corpus hiện tại; cần xây dựng lại index.",
                index_version=managed_index.version_id,
                corpus_revision=current_revision,
            )

        if active_artifacts.document_count == 0 or active_artifacts.matrix.shape[0] == 0:
            return _response(
                "empty_corpus",
                "Corpus hiện chưa có tài liệu để tìm kiếm.",
                index_version=managed_index.version_id,
                corpus_revision=current_revision,
            )

        vocabulary = set(active_artifacts.vectorizer.get_feature_names_out())
        query_terms = processed_query.split()
        if not query_terms or not any(term in vocabulary for term in query_terms):
            return _response(
                "oov_query",
                "Không có từ khóa nào trong truy vấn thuộc vocabulary của hệ thống.",
                index_version=managed_index.version_id,
                corpus_revision=current_revision,
            )

        try:
            engine = create_search_engine(active_artifacts, managed_index.inverted_index)
            results = search(engine, processed_query, top_k=top_k)
        except Exception as exc:
            return _response(
                "index_unavailable",
                f"Không thể thực hiện tìm kiếm với chỉ mục hiện tại: {exc}",
                index_version=managed_index.version_id,
                corpus_revision=current_revision,
            )

        return _response(
            "ok",
            "Tìm kiếm thành công." if results else "Không tìm thấy tài liệu phù hợp.",
            results=results,
            index_version=managed_index.version_id,
            corpus_revision=current_revision,
        )


_default_engine: RetrievalEngine | None = None


def search_query(query: str, top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
    """Module-level API requested by TV3: ``search_query(query, top_k)``."""
    global _default_engine
    if _default_engine is None:
        _default_engine = RetrievalEngine()
    return _default_engine.search_query(query, top_k)
