"""Inverted-index utilities for the SmartDoc TV2 retrieval engine.

This module builds a term -> document-ID mapping from an already-fitted TF-IDF
artifact. It does not preprocess text, fit TF-IDF, or access the database.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
from scipy import sparse

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tfidf_engine import TfidfArtifacts


class InvertedIndexError(ValueError):
    """Base error for invalid inverted-index input."""


class InvalidInvertedIndexInputError(InvertedIndexError):
    """Raised when the supplied TF-IDF data is inconsistent."""


@dataclass(frozen=True)
class InvertedIndex:
    """Immutable inverted index.

    Attributes:
        postings: Mapping from vocabulary term to sorted document IDs that
            have a non-zero TF-IDF weight for that term.
        ordered_document_ids: Document IDs in the exact row order of the
            source TF-IDF matrix.
        terms: Vocabulary terms in the exact column order of that matrix.
    """

    postings: Mapping[str, tuple[int, ...]]
    ordered_document_ids: tuple[int, ...]
    terms: tuple[str, ...]

    def __post_init__(self) -> None:
        # Copy the mapping so callers cannot mutate the original dictionary
        # and accidentally change an index after construction.
        copied = {term: tuple(ids) for term, ids in self.postings.items()}
        object.__setattr__(self, "postings", copied)


def build_inverted_index(artifacts: "TfidfArtifacts") -> InvertedIndex:
    """Build a term -> document-ID index from fitted TF-IDF artifacts.

    A document is included in a term's posting list when the corresponding
    TF-IDF matrix cell is non-zero. Document IDs in every posting list are
    sorted ascending, independently of matrix row order.
    """
    try:
        vectorizer = artifacts.vectorizer
        matrix = artifacts.matrix
        document_ids = tuple(artifacts.ordered_document_ids)
    except AttributeError as exc:
        raise InvalidInvertedIndexInputError(
            "artifacts must provide vectorizer, matrix, and ordered_document_ids"
        ) from exc

    if not sparse.issparse(matrix):
        raise InvalidInvertedIndexInputError("TF-IDF matrix must be a SciPy sparse matrix")
    if len(document_ids) != matrix.shape[0]:
        raise InvalidInvertedIndexInputError(
            "ordered_document_ids length must match the number of matrix rows"
        )
    if any(isinstance(doc_id, bool) or not isinstance(doc_id, (int, np.integer))
           for doc_id in document_ids):
        raise InvalidInvertedIndexInputError("document IDs must be integers")
    if len(set(int(doc_id) for doc_id in document_ids)) != len(document_ids):
        raise InvalidInvertedIndexInputError("document IDs must be unique")

    try:
        terms = tuple(str(term) for term in vectorizer.get_feature_names_out())
    except Exception as exc:
        raise InvalidInvertedIndexInputError(
            "vectorizer must expose get_feature_names_out()"
        ) from exc

    if len(terms) != matrix.shape[1]:
        raise InvalidInvertedIndexInputError(
            "vocabulary size must match the number of matrix columns"
        )

    postings: dict[str, list[int]] = {term: [] for term in terms}
    csc = matrix.tocsc(copy=True)
    csc.sum_duplicates()
    csc.eliminate_zeros()

    for column, term in enumerate(terms):
        start, end = csc.indptr[column], csc.indptr[column + 1]
        row_indices = csc.indices[start:end]
        ids = sorted(int(document_ids[row]) for row in row_indices)
        if ids:
            postings[term] = ids

    # Empty posting lists are omitted: absent terms naturally yield no candidates.
    compact_postings = {
        term: tuple(ids) for term, ids in postings.items() if ids
    }
    return InvertedIndex(
        postings=compact_postings,
        ordered_document_ids=tuple(int(doc_id) for doc_id in document_ids),
        terms=terms,
    )


def get_candidates(
    index: InvertedIndex,
    query_terms: Iterable[str],
) -> tuple[int, ...]:
    """Return sorted unique document IDs containing any query term.

    Terms not present in the index are ignored. If no query term has postings,
    an empty tuple is returned.
    """
    if not isinstance(index, InvertedIndex):
        raise InvalidInvertedIndexInputError("index must be an InvertedIndex instance")

    candidates: set[int] = set()
    for term in query_terms:
        if not isinstance(term, str):
            raise InvalidInvertedIndexInputError("query terms must be strings")
        candidates.update(index.postings.get(term, ()))
    return tuple(sorted(candidates))


def get_postings(index: InvertedIndex, term: str) -> tuple[int, ...]:
    """Return a term's posting list, or an empty tuple if it is absent."""
    if not isinstance(index, InvertedIndex):
        raise InvalidInvertedIndexInputError("index must be an InvertedIndex instance")
    if not isinstance(term, str):
        raise InvalidInvertedIndexInputError("term must be a string")
    return index.postings.get(term, ())
