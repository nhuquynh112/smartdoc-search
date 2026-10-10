"""Query-time TF-IDF retrieval and ranking for SmartDoc TV2.

This module consumes the artifacts from ``tfidf_engine`` and the candidate
postings from ``inverted_index``. It does not access the database or rebuild
the index.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from .inverted_index import InvertedIndex, get_candidates


class SearchEngineError(ValueError):
    """Base exception for query-time search errors."""


class InvalidSearchInputError(SearchEngineError):
    """Raised when query parameters or index artifacts are inconsistent."""


@dataclass(frozen=True)
class SearchEngine:
    """A fitted vectorizer, TF-IDF matrix, document IDs, and inverted index."""

    vectorizer: TfidfVectorizer
    matrix: sparse.spmatrix
    ordered_document_ids: tuple[int, ...]
    inverted_index: InvertedIndex

    def __post_init__(self) -> None:
        if not sparse.issparse(self.matrix):
            raise InvalidSearchInputError("TF-IDF matrix must be sparse")
        if self.matrix.shape[0] != len(self.ordered_document_ids):
            raise InvalidSearchInputError(
                "document ID count must match the number of TF-IDF matrix rows"
            )
        if len(set(self.ordered_document_ids)) != len(self.ordered_document_ids):
            raise InvalidSearchInputError("document IDs must be unique")
        if tuple(self.inverted_index.ordered_document_ids) != tuple(self.ordered_document_ids):
            raise InvalidSearchInputError(
                "inverted-index document IDs must match TF-IDF matrix row order"
            )
        if self.matrix.shape[1] != len(self.vectorizer.get_feature_names_out()):
            raise InvalidSearchInputError(
                "TF-IDF matrix columns must match vectorizer vocabulary size"
            )


def create_search_engine(artifacts, inverted_index: InvertedIndex) -> SearchEngine:
    """Create a query-time search engine from fitted artifacts and an index."""
    try:
        vectorizer = artifacts.vectorizer
        matrix = artifacts.matrix
        document_ids = tuple(int(value) for value in artifacts.ordered_document_ids)
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidSearchInputError(
            "artifacts must provide vectorizer, matrix, and ordered_document_ids"
        ) from exc

    return SearchEngine(
        vectorizer=vectorizer,
        matrix=matrix,
        ordered_document_ids=document_ids,
        inverted_index=inverted_index,
    )


def search(
    engine: SearchEngine,
    query: str,
    top_k: int = 5,
) -> list[dict[str, int | float]]:
    """Search for query terms and return positive-score results ranked by score.

    Result shape is exactly ``document_id``, ``score``, and ``rank``.
    Ties are resolved by ascending document ID. Non-positive scores are omitted.
    """
    if not isinstance(engine, SearchEngine):
        raise InvalidSearchInputError("engine must be a SearchEngine instance")
    if not isinstance(query, str):
        raise InvalidSearchInputError("query must be a string")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise InvalidSearchInputError("top_k must be a positive integer")

    normalized_query = query.strip()
    if not normalized_query or engine.matrix.shape[0] == 0 or engine.matrix.shape[1] == 0:
        return []

    # Documents are already preprocessed by TV1. Query tokens must use the same
    # whitespace-tokenized representation; do not invoke Underthesea here.
    query_tokens = normalized_query.split()
    vocabulary = set(engine.vectorizer.get_feature_names_out())
    known_query_terms = [term for term in query_tokens if term in vocabulary]
    if not known_query_terms:
        return []

    candidate_ids = get_candidates(engine.inverted_index, known_query_terms)
    if not candidate_ids:
        return []

    id_to_row = {doc_id: row for row, doc_id in enumerate(engine.ordered_document_ids)}
    try:
        candidate_rows = np.asarray([id_to_row[doc_id] for doc_id in candidate_ids], dtype=np.int64)
    except KeyError as exc:
        raise InvalidSearchInputError(
            "inverted index contains a document ID absent from TF-IDF artifacts"
        ) from exc

    # transform() uses the fitted vectorizer's IDF and vocabulary. Since the
    # fitted vectorizer's tokenizer is str.split, this does not re-tokenize text.
    query_vector = engine.vectorizer.transform([normalized_query])
    if query_vector.nnz == 0:
        return []

    candidate_matrix = engine.matrix[candidate_rows]
    scores = (candidate_matrix @ query_vector.T).toarray().ravel()

    ranked: list[tuple[int, float]] = []
    for doc_id, score in zip(candidate_ids, scores):
        numeric_score = float(score)
        if numeric_score > 0.0:
            ranked.append((int(doc_id), numeric_score))

    ranked.sort(key=lambda item: (-item[1], item[0]))
    ranked = ranked[:top_k]
    return [
        {"document_id": doc_id, "score": score, "rank": rank}
        for rank, (doc_id, score) in enumerate(ranked, start=1)
    ]


def search_brute_force(
    engine: SearchEngine,
    query: str,
    top_k: int = 5,
) -> list[dict[str, int | float]]:
    """Reference implementation scoring every document for correctness tests.

    This is intentionally simple and intended for validation, not production
    candidate pruning. It uses the same fitted vectorizer and ranking rules.
    """
    if not isinstance(engine, SearchEngine):
        raise InvalidSearchInputError("engine must be a SearchEngine instance")
    if not isinstance(query, str):
        raise InvalidSearchInputError("query must be a string")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise InvalidSearchInputError("top_k must be a positive integer")

    normalized_query = query.strip()
    if not normalized_query or engine.matrix.shape[0] == 0 or engine.matrix.shape[1] == 0:
        return []

    query_vector = engine.vectorizer.transform([normalized_query])
    if query_vector.nnz == 0:
        return []

    scores = (engine.matrix @ query_vector.T).toarray().ravel()
    ranked = [
        (int(doc_id), float(score))
        for doc_id, score in zip(engine.ordered_document_ids, scores)
        if float(score) > 0.0
    ]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    ranked = ranked[:top_k]
    return [
        {"document_id": doc_id, "score": score, "rank": rank}
        for rank, (doc_id, score) in enumerate(ranked, start=1)
    ]
